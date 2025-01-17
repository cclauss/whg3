# collection.views (collections)
import os
import requests

from dateutil.parser import isoparse
from datetime import date
import json
import random

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms.models import inlineformset_factory
from django.http import JsonResponse, HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import (View, CreateView, UpdateView, DetailView, DeleteView, ListView )

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.db.models import Extent

from .forms import CollectionModelForm, CollectionGroupModelForm
from .models import *
from datasets.tasks import index_dataset_to_builder
from main.models import Log, Link
from traces.forms import TraceAnnotationModelForm
from traces.models import TraceAnnotation

""" collection group joiner"; prevent duplicate """
def join_group(request, *args, **kwargs):
  print('join_group() kwargs', kwargs)
  print('join_group() request.POST', request.POST)

  entered_code = request.POST.get('join_code', None)
  if entered_code is None:
    return JsonResponse({'msg': 'No code provided'}, safe=False)

  try:
    cg = CollectionGroup.objects.get(join_code=entered_code)
  except CollectionGroup.DoesNotExist:
    return JsonResponse({'msg': 'Unknown code'}, safe=False)

  user = request.user
  # Check if the user is already a member of the group
  existing_membership = CollectionGroupUser.objects.filter(user=user, collectiongroup=cg).exists()
  if existing_membership:
    return JsonResponse({
      'status': 'already_member',
      'msg': 'You are already a member of group "<b>' + cg.title + '</b>"!',
      'cg_title': cg.title,
      'cg_id': cg.id,
    }, safe=False)

  cgu = CollectionGroupUser.objects.create(
    user=user, collectiongroup=cg, role='member')
  return JsonResponse({
    'status': 'success',
    'msg': 'Joined group ' + cg.title + '!',
    'cg_title': cg.title,
    'cg_id': cg.id,
  }, safe=False)

# def join_group(request, *args, **kwargs):
#   print('join_group() kwargs', kwargs)
#   print('join_group() request.POST', request.POST)
#
#   entered_code = request.POST.get('join_code', None)
#   if entered_code is None:
#     return JsonResponse({'msg': 'No code provided'}, safe=False)
#
#   try:
#     cg = CollectionGroup.objects.get(join_code=entered_code)
#   except CollectionGroup.DoesNotExist:
#     return JsonResponse({'msg': 'Unknown code'}, safe=False)
#
#   user = request.user
#   cgu = CollectionGroupUser.objects.create(
#     user=user, collectiongroup=cg, role='member')
#   return JsonResponse({
#     'msg': 'Joined group '+cg.title+'!',
#     'cg_title': cg.title,
#     'cg_id': cg.id,
#   }, safe=False)


"""collection group join code generator"""
adjectives = ['Swift', 'Wise', 'Clever', 'Eager', 'Gentle', 'Smiling', 'Lucky', 'Brave', 'Happy']
nouns = ['Wolf', 'Deer', 'Swan', 'Cat', 'Owl', 'Bear', 'Rabbit', 'Lion', 'Horse', 'Dog', 'Duck', 'Hawk', 'Eagle', 'Fox', 'Tiger', 'Goose']
def generate_unique_join_code(request):
  while True:
    adjective = random.choice(adjectives)
    noun = random.choice(nouns)
    join_code = adjective + noun
    if not CollectionGroup.objects.filter(join_code=join_code).exists():
      return JsonResponse({'join_code': join_code})

""" collection group join code setter """
def set_joincode(request, *args, **kwargs):
  print('set_joincode() kwargs', kwargs)
  cg = CollectionGroup.objects.get(id=kwargs['cgid'])
  cg.join_code = kwargs['join_code']
  cg.save()
  return JsonResponse({'join_code': cg.join_code})

""" sets collection to inactive, removing from lists """
def inactive(request, *args, **kwargs):
  print('inactive() request.POST', request.POST)
  coll = Collection.objects.get(id=request.POST['id'])
  coll.active = False
  coll.save()
  result = {"msg": "collection " + coll.title + '('+str(coll.id)+') flagged inactive'}
  return JsonResponse(result, safe=False)

""" removes dataset from collection, refreshes page"""
def remove_link(request, *args, **kwargs):
  #print('kwargs', kwargs)
  link = Link.objects.get(id=kwargs['id'])
  # link = CollectionLink.objects.get(id=kwargs['id'])
  print('remove_link()', link)
  link.delete()
  return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

"""
  set collection status by group leader: reviewed, nominated
"""
def status_update(request, *args, **kwargs):
  print('in status_update()', request.POST)
  status = request.POST['status']
  coll = Collection.objects.get(id=request.POST['coll'])

  coll.status = status
  coll.save()

  return JsonResponse({'status': status, 'coll': coll.title}, safe=False,
                      json_dumps_params={'ensure_ascii': False, 'indent': 2})

"""
  set/unset nominated flag by group leader: boolean
"""
def nominator(request, *args, **kwargs):
  print('in nominator()', request.POST)
  nominated = True if request.POST['nominated'] == 'true' else False
  coll = Collection.objects.get(id=request.POST['coll'])
  print('nominated?', nominated, 'coll', coll.title, 'id', coll.id)
  if nominated:
    coll.nominated = True
    coll.status = 'nominated'
  else:
    coll.nominated = False
    coll.status = 'reviewed'
  coll.save()

  return JsonResponse({'status': coll.status, 'coll': coll.title}, safe=False,
                      json_dumps_params={'ensure_ascii': False, 'indent': 2})


"""
  user adds (submits) or removes collection to/from collection group
"""
def group_connect(request, *args, **kwargs):
  action = request.POST['action']
  print('group_connect() action', action)
  coll = Collection.objects.get(id=request.POST['coll'])
  cg = CollectionGroup.objects.get(id=request.POST['group'])
  if action == 'submit':
    cg.collections.add(coll)
    coll.status = 'group'
    coll.save()
    status = 'added to'
  else:
    cg.collections.remove(coll)
    coll.group = None
    coll.submit_date = None
    coll.status = 'sandbox'
    coll.save()
    status = 'removed from'

  return JsonResponse({'status': status, 'coll': coll.title, 'group': cg.title}, safe=False,
                      json_dumps_params={'ensure_ascii': False, 'indent': 2})

"""
  add collaborator to collection in role
"""
def collab_add(request, cid):
  print('collab_add() request.POST, cid', request.POST, cid)
  username = request.POST['username']
  response_data = {}
  try:
    user = get_object_or_404(User, username=username)
    uid = user.id
    role = request.POST['role']
  except Http404:
      response_data['status'] = 'User "'+username+'" not found'
      return JsonResponse(response_data)

  is_already_collaborator = CollectionUser.objects.filter(user_id=uid, collection_id=cid).exists()
  if is_already_collaborator:
      response_data['status'] = 'User is already a collaborator'
      return JsonResponse(response_data)

  response_data['status'] = 'ok'

  # TODO: send collaborator an email
  print('collection collab_add():', request.POST['username'],role, cid, uid)
  coll_collab = CollectionUser.objects.create(user_id=uid, collection_id=cid, role=role)
  response_data['user'] = str(coll_collab)  # name (role, email)
  response_data['uid'] = uid
  response_data['cid'] = cid

  return JsonResponse(response_data)

"""
  collab_remove(uid, cid)
  remove collaborator from collection
"""
def collab_remove(request, uid, cid):
  print('collab_delete() request, uid, cid', request, uid, cid)
  get_object_or_404(CollectionUser,user=uid, collection=cid).delete()
  response_data = {"status": "ok", "uid": uid}
  return JsonResponse(response_data)

""" utility: get next sequence for a collection """
def seq(coll):
  cps = CollPlace.objects.filter(collection=coll).values_list("sequence",flat=True)
  if cps:
    next=max(cps)+1
  else:
    next=0
  print(next)
  return next

"""
  add list of >=1 places to collection
  i.e. new CollPlace and TraceAnnotation rows
  ajax call from ds_places.html and place_portal.html
"""
# TODO: essentially same as add_dataset(); needs refactor
def add_places(request, *args, **kwargs):
  print('args', args)
  print('kwargs', kwargs)
  if request.method == 'POST':
    user = request.user
    status, msg = ['', '']
    dupes = []
    added = []
    # print('add_places request', request.POST)
    coll = Collection.objects.get(id=request.POST['collection'])
    place_list = [int(i) for i in request.POST['place_list'].split(',')]
    for p in place_list:
      place = Place.objects.get(id=p)
      print('got place', place.title, 'in collection', coll.title, 'id', coll.id)
      gotplace = TraceAnnotation.objects.filter(collection=coll, place=place, archived=False)
      if not gotplace:
        t = TraceAnnotation.objects.create(
          place = place,
          src_id = place.src_id,
          collection = coll,
          motivation = 'locating',
          owner = user,
          anno_type = 'place',
          saved = 0
        )
        # coll.places.add(p)
        CollPlace.objects.create(
          collection=coll,
          place=place,
          sequence=seq(coll)
        )
        added.append(p)
      else:
        dupes.append(place.title)
      print('add_places() result', {"added": added, "dupes": dupes})
      msg = {"added": added, "dupes": dupes}
    return JsonResponse({'status': status, 'msg': msg}, safe=False)

"""
  deletes CollPlace record(s) and
  archives TraceAnnotation(s) for list of pids
"""
def archive_traces(request, *args, **kwargs):
  if request.method == 'POST':
    print('archive_traces request', request.POST)
    coll = Collection.objects.get(id=request.POST['collection'])
    place_list = [int(i) for i in request.POST['place_list'].split(',')]
    print('place_list to remove', place_list)
    # remove CollPlace, archive TraceAnnotation
    for pid in place_list:
      place = Place.objects.get(id=pid)
      if place in coll.places.all():
        # print('collection place', place)
        coll.places.remove(place)
      if place.traces:
        # can be only one but .update only works on filter
        TraceAnnotation.objects.filter(collection=coll,place=place).update(archived=True)
    return JsonResponse({'result': str(len(place_list))+' places removed, we think'}, safe=False)

""" update sequence of annotated places """
def update_sequence(request, *args, **kwargs):
  print('request.POST', request.POST)
  new_sequence = json.loads(request.POST['seq'])
  # print('new_sequence', new_sequence)
  cid = request.POST['coll_id']
  for cp in CollPlace.objects.filter(collection=cid):
    cp.sequence = new_sequence[str(cp.place_id)]
    cp.save()
  return JsonResponse({"msg": "updated?", "POST": new_sequence})

"""
create place collection on the fly; return id for adding place(s) to it
"""
def flash_collection_create(request, *args, **kwargs):
  print('flash_collection_create request.POST', request.POST)
  print('flash_collection_create kwargs', kwargs)
  if request.method == 'POST':
    collobj = Collection.objects.create(
      owner = request.user,
      title = request.POST['title'],
      collection_class = 'place',
      description = 'new collection',
      # keywords = '{replace, these, please}'
    )
    collobj.save()
    result = {"id": collobj.id, 'title': collobj.title}
  return JsonResponse(result, safe=False)

def stringer(str):
  if str:
    return isoparse(str).strftime('%Y' if len(str)<=5 else '%b %Y' if len(str)<=8 else '%d %b %Y')
  else:
    return None
def when_format(ts):
  return [stringer(ts[0]), stringer(ts[1])]; print(result)
def year_from_string(ts):
  if ts:
    return int(isoparse(ts).strftime('%Y'))
  else:
    return "null" # String required by Maplibre filter test

# GeoJSON for all places in a collection INCLUDING those without geometry
def fetch_mapdata_coll(request, *args, **kwargs):
  from django.core.serializers import serialize
  from django.db.models import Min, Max
  print('fetch_geojson_coll kwargs',kwargs)
  id_=kwargs['id']
  coll=get_object_or_404(Collection, id=id_)
  rel_keywords = coll.rel_keywords

  tileset = request.GET.get('variant', '') == 'tileset'
  ignore_tilesets = request.GET.get('variant', '') == 'ignore_tilesets'

  ############################################################################################################
  # TODO: Force `ignore_tilesets` if any `visParameters` object has 'trail: true'                            #
  # (representative points have to be generated in the browser)                                              #
  ############################################################################################################

  available_tilesets = None
  null_geometry = False
  if not tileset and not ignore_tilesets:

    tiler_url = os.environ.get('TILER_URL') # Must be set in /.env/.dev-whg3
    response = requests.post(tiler_url, json={"getTilesets": {"type": "collections", "id": id_}})

    if response.status_code == 200:
        available_tilesets = response.json().get('tilesets', [])
        null_geometry = len(available_tilesets) > 0

  extent = list(coll.places_all.aggregate(Extent('geoms__geom')).values())[0]

  annotated_places = coll.places_all.annotate(seq=Min('annos__sequence')).order_by('seq')

  feature_collection = {
    "title": coll.title,
    "creator": coll.creator,
    "type": "FeatureCollection",
    "features": [],
    "relations": coll.rel_keywords,
    "extent": extent,
  }

  if null_geometry:
    feature_collection["tilesets"] = available_tilesets

  for i, t in enumerate(coll.traces.filter(archived=False)):
    # Get the first annotation's sequence value
    first_anno = t.place.annos.first()
    sequence_value = first_anno.sequence if first_anno else None
    
    geoms = t.place.geoms.all()
    geometry = t.place.geoms.all()[0].jsonb if geoms else None # some places have no geometry

    feature = {
          "type": "Feature",
          "geometry": geometry,
          "properties": {
              "pid": t.place.id,
              "cid": id_,
              "title": t.place.title,
              "ccodes": t.place.ccodes,
              "relation": t.relation[0] if t.relation else None,
              "min": year_from_string(t.start),
              "max": year_from_string(t.end),
              "note": t.note,
              "seq": sequence_value,
          },
          "id": i,  # Required for MapLibre conditional styling
    }

    if null_geometry: # Minimise data sent to browser when using a vector tileset
        if geometry:
            del feature["geometry"]["coordinates"]
            if "geowkt" in feature["geometry"]:
                del feature["geometry"]["geowkt"]
    elif tileset: # Minimise data to be included in a vector tileset
        # Drop all properties except any listed here
        properties_to_keep = ["pid"] # Perhaps ["pid", "min", "max"]
        feature["properties"] = {k: v for k, v in feature["properties"].items() if k in properties_to_keep}

    feature_collection["features"].append(feature)

  return JsonResponse(feature_collection, safe=False, json_dumps_params={'ensure_ascii':False,'indent':2})

""" gl map needs this """
# TODO:
def fetch_geojson_coll(request, *args, **kwargs):
  # print('fetch_geojson_coll kwargs',kwargs)
  id_=kwargs['id']
  coll=get_object_or_404(Collection, id=id_)
  rel_keywords = coll.rel_keywords

  features_t = [
    {
        "type": "Feature",
        "geometry": t.place.geoms.all()[0].jsonb,
        "properties":{
            "pid":t.place.id,
            "title": t.place.title,
            "relation": t.relation[0],
            "when": when_format([t.start, t.end]),
            "note": t.note
        }
    }
    for t in coll.traces.filter(archived=False)
  ]

  feature_collection = {
    "type": "FeatureCollection",
    "features": features_t,
    "relations": coll.rel_keywords,
  }

  return JsonResponse(feature_collection, safe=False, json_dumps_params={'ensure_ascii':False,'indent':2})

""" returns json for display """
class ListDatasetView(View):
  @staticmethod
  def get(request):
    print('ListDatasetView() GET', request.GET)
    #coll = Collection.objects.get(id=request.GET['coll_id'])
    ds = Dataset.objects.get(id=request.GET['ds_id'])
    #coll.datasets.add(ds)
    result = {
      "id": ds.id,
      "label": ds.label,
      "title": ds.title,
      "create_date": ds.create_date,
      "description": ds.description[:100]+'...',
      "numrows": ds.places.count()
    }
    return JsonResponse(result, safe=False)

"""
  adds all places in a dataset as CollPlace records
  to a place collection
  i.e. new CollPlace and TraceAnnotation rows
  url call from place_collection_build.html
  adds dataset to db:collections_datasets
"""
# TODO: essentially same as add_places(); needs refactor
def add_dataset_places(request, *args, **kwargs):
  print('method', request.method)
  print('add_dataset() kwargs', kwargs)
  coll = Collection.objects.get(id=kwargs['coll_id'])
  ds = Dataset.objects.get(id=kwargs['ds_id'])
  user = request.user
  print('add_dataset(): coll, ds', coll, ds)
  status, msg = ['', '']
  dupes = []
  added = []
  coll.datasets.add(ds)
  for place in ds.places.all():
    # has non-archived trace annotation?
    gottrace = TraceAnnotation.objects.filter(collection=coll, place=place, archived=False)
    if not gottrace:
      t = TraceAnnotation.objects.create(
        place=place,
        src_id=place.src_id,
        collection=coll,
        motivation='locating',
        owner=user,
        anno_type='place',
        saved=0
      )
      # coll.places.add(p)
      CollPlace.objects.create(
        collection=coll,
        place=place,
        sequence=seq(coll)
      )
      added.append(place.id)
    else:
      dupes.append(place.title)
    msg = {"added": added, "dupes": dupes}
  # return JsonResponse({'status': status, 'msg': msg}, safe=False)
  return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

"""
  adds dataset to dataset collection
  - if it is the first in
  - if no incomplete reviews of @align_builder tasks
"""

def add_dataset(request, *args, **kwargs):
  coll = Collection.objects.get(id=kwargs['coll_id'])
  ds = Dataset.objects.get(id=kwargs['ds_id'])
  print('add_dataset(): ds ' + str(ds) + ' to coll ' + str(coll))

  if not coll.datasets.filter(id=ds.id).exists():
    coll.datasets.add(ds)
    sequence = coll.datasets.count()
    if coll.datasets.count() == 1:
      # index only the first
      indexing_result = index_dataset_to_builder(ds.id, coll.id)
    dataset_details = {
      "id": ds.id,
      "label": ds.label,
      "title": ds.title,
      "create_date": ds.create_date,
      "description": ds.description[:100]+'...',
      "numrows": ds.places.count(),
      "sequence": sequence
    }
    return JsonResponse({'status': 'success',
                         'dataset': dataset_details})

  return JsonResponse({'status': 'already_added'})


"""
  removes dataset from collection
  clean up "omitted"; refreshes page
"""
def remove_dataset(request, *args, **kwargs):
  coll = Collection.objects.get(id=kwargs['coll_id'])
  ds = Dataset.objects.get(id=kwargs['ds_id'])
  print('remove_dataset(): coll, ds', coll, ds)

  # remove CollPlace records
  CollPlace.objects.filter(place_id__in=ds.placeids).delete()
  # remove dataset from collections_dataset
  coll.datasets.remove(ds)
  # archive any non-blank trace annotations
  # someone will want to recover them, count on it
  current_traces = coll.traces.filter(collection=coll, place__in=ds.placeids)
  non_blank = [t.id for t in current_traces.all() if t.blank == False]
  blanks = current_traces.exclude(id__in=non_blank)
  if non_blank:
    current_traces.filter(id__in=non_blank).update(archived=True)
    current_traces.filter(archived=False).delete()
  blanks.delete()
  return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

def create_collection_group(request, *args, **kwargs):
  # must be member of group_leaders
  result = {"status": "", "id": "", 'title': ""}
  if request.method == 'POST':
    print('request.POST', request.POST)
    owner = get_user_model().objects.get(id=request.POST['ownerid'])
    group_title = request.POST['title']
    description = request.POST['description']
    if group_title in CollectionGroup.objects.all().values_list('title', flat=True):
      result['status'] = "dupe"
    else:
      newgroup = CollectionGroup.objects.create(
        owner = owner,
        title = group_title,
        description = description,
      )
      # newgroup.user_set.add(request.user)
      result = {"status": "ok", "id": newgroup.id, 'title': newgroup.title}

  return JsonResponse(result, safe=False)

CollectionLinkFormset = inlineformset_factory(
    Collection, CollectionLink, fields=('uri','label','link_type'), extra=2,
    widgets={
      'link_type': forms.Select(choices=('webpage'))}
)

"""
  PLACE COLLECTIONS
  collections from places and/or datasets; uses place_collection_build.html
"""
# TODO: refactor to fewer views
class PlaceCollectionCreateView(LoginRequiredMixin, CreateView):
  form_class = CollectionModelForm
  template_name = 'collection/place_collection_build.html'
  queryset = Collection.objects.all()

  def get_form_kwargs(self, **kwargs):
    kwargs = super(PlaceCollectionCreateView, self).get_form_kwargs()
    return kwargs

  def get_context_data(self, *args, **kwargs):
    user = self.request.user
    print('PlaceCollectionCreateView() user', user)
    context = super(PlaceCollectionCreateView, self).get_context_data(**kwargs)
    context['mbtoken'] = settings.MAPBOX_TOKEN_MB

    datasets = []
    # add 1 or more links, images (?)
    if self.request.POST:
      context["links_form"] = CollectionLinkFormset(self.request.POST)
      # context["images_form"] = CollectionImageFormset(self.request.POST)
    else:
      context["links_form"] = CollectionLinkFormset()
      # context["images_form"] = CollectionImageFormset()

    # owners create collections from their datasets
    ds_select = [obj for obj in Dataset.objects.all().order_by('title') if user in obj.owners or user.is_superuser]
    if not user.is_superuser:
      ds_select.insert(len(ds_select)-1, Dataset.objects.get(label='owt10'))

    context['action'] = 'create'
    context['ds_select'] = ds_select
    context['coll_dsset'] = datasets

    return context

  def form_valid(self, form):
    context = self.get_context_data()
    self.object = form.save()

    # TODO: write log entry
    # Log.objects.create(
    #   # category, logtype, "timestamp", subtype, dataset_id, user_id
    #   category='collection',
    #   logtype='coll_create',
    #   subtype='place',
    #   coll_id=self.object.id,
    #   user_id=self.request.user.id
    # )

    print('form is valid, cleaned_data',form.cleaned_data)
    print('referrer', self.request.META.get('HTTP_REFERER'))
    return super().form_valid(form)

  def form_invalid(self,form):
    context = self.get_context_data()
    context['errors'] = form.errors
    print('form invalid...',form.errors.as_data())
    context = {'form': form}
    return self.render_to_response(context=context)

  def get_success_url(self):
    Log.objects.create(
      # category, logtype, "timestamp", subtype, note, dataset_id, user_id
      category = 'collection',
      logtype = 'create',
      note = 'created collection id: '+str(self.object.id),
      user_id = self.request.user.id
    )
    # return to update page after create
    return reverse('collection:place-collection-update', kwargs = {'id':self.object.id})

""" update place collection; uses place_collection_build.html """
class PlaceCollectionUpdateView(LoginRequiredMixin, UpdateView):
  form_class = CollectionModelForm
  template_name = 'collection/place_collection_build.html'
  queryset = Collection.objects.all()

  def get_form_kwargs(self, **kwargs):
    kwargs = super(PlaceCollectionUpdateView, self).get_form_kwargs()
    kwargs.update({'user': self.request.user})
    return kwargs

  def get_object(self):
    id_ = self.kwargs.get("id")
    return get_object_or_404(Collection, id=id_)

  def form_invalid(self, form):
    print('form invalid...', form.errors.as_data())
    context = {'form': form}
    return self.render_to_response(context=context)

  def form_valid(self, form):
    data = form.cleaned_data
    print('cleaned_data', data)
    print('referrer', self.request.META.get('HTTP_REFERER'))
    id_ = self.kwargs.get("id")
    obj = form.save(commit=False)
    if obj.group:
      obj.status = 'group'
      obj.submit_date = date.today()
    else:
      obj.status = 'sandbox'
      obj.nominated = False
      obj.submit_date = None
    obj.save()

    Log.objects.create(
      # category, logtype, "timestamp", subtype, note, dataset_id, user_id
      category = 'collection',
      logtype = 'update',
      note = 'collection id: '+ str(obj.id) + ' by '+ self.request.user.name,
      user_id = self.request.user.id
    )
    # return to page, or to browse
    if 'update' in self.request.POST:
      return redirect('/collections/' + str(id_) + '/update_pl')
    else:
      return redirect('/collections/' + str(id_) + '/browse_pl')

  def get_context_data(self, *args, **kwargs):
    context = super(PlaceCollectionUpdateView, self).get_context_data(*args, **kwargs)
    user = self.request.user
    _id = self.kwargs.get("id")
    coll = self.object
    datasets = self.object.datasets.all()
    in_class = coll.group.type == 'class' if coll.group else False
    form_anno = TraceAnnotationModelForm(self.request.GET or None, auto_id="anno_%s")
    # populates dropdown
    ds_select = [obj for obj in Dataset.objects.all().order_by('title') if user in obj.owners or user.is_superuser]
    if not user.is_superuser:
      ds_select.insert(len(ds_select)-1, Dataset.objects.get(label='owt10'))

    context['action'] = 'update'
    context['ds_select'] = ds_select
    context['coll_dsset'] = datasets
    context['links'] = Link.objects.filter(collection=coll.id)

    context['owner'] = True if user == coll.owner else False
    context['is_owner'] = True if user in self.object.owners else False
    context['is_member'] = True if user in coll.owners or user in coll.collaborators else False
    context['whgteam'] = True if user.groups.filter(name__in=['whg_team','editorial']).exists() else False
    context['whg_admins'] = True if user.groups.filter(name__in=['whg_admins','editorial']).exists() else False
    context['collabs'] = CollectionUser.objects.filter(collection=coll.id)
    context['mygroups'] = CollectionGroupUser.objects.filter(user_id=user)
    context['in_class'] = in_class
    # context['links'] = CollectionLink.objects.filter(collection=self.object.id)

    context['form_anno'] = form_anno
    context['seq_places'] = [
      {'id':cp.id,'p':cp.place,'seq':cp.sequence}
        for cp in CollPlace.objects.filter(collection=_id).order_by('sequence')
    ]
    context['created'] = self.object.created.strftime("%Y-%m-%d")
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY
    # context['whgteam'] = User.objects.filter(groups__name='whg_team')

    return context

""" browse collection *all* places """
class PlaceCollectionBrowseView(DetailView):
  login_url = '/accounts/login/'
  redirect_field_name = 'redirect_to'

  model = Collection
  template_name = 'collection/place_collection_browse.html'

  def get_success_url(self):
    id_ = self.kwargs.get("id")
    return '/collections/'+str(id_)+'/places'

  def get_object(self):
    id_ = self.kwargs.get("id")
    return get_object_or_404(Collection, id=id_)

  def get_context_data(self, *args, **kwargs):
    id_ = self.kwargs.get("id")
    coll = get_object_or_404(Collection, id=id_)

    context = super(PlaceCollectionBrowseView, self).get_context_data(*args, **kwargs)
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY
    context['media_url'] = settings.MEDIA_URL

    context['is_admin'] = True if self.request.user.groups.filter(name__in=['whg_admins']).exists() else False
    context['ds_list'] = coll.ds_list
    context['ds_counter'] = coll.ds_counter
    context['collabs'] = coll.collaborators.all()
    context['images'] = [ta.image_file.name for ta in coll.traces.all()]
    context['links'] = coll.related_links.all()
    context['places'] = coll.places.all().order_by('title')
    context['updates'] = {}
    context['url_front'] = settings.URL_FRONT

    #if not coll.vis_parameters:
        # Populate with default values:
        # tabulate: 'initial'|true|false - include sortable table column, 'initial' indicating the initial sort column
        # temporal_control: 'player'|'filter'|null - control to be displayed when sorting on this column
        # trail: true|false - whether to include ant-trail motion indicators on map
        #coll.vis_parameters = "{'seq': {'tabulate': false, 'temporal_control': 'player', 'trail': true},'min': {'tabulate': 'initial', 'temporal_control': 'player', 'trail': true},'max': {'tabulate': true, 'temporal_control': 'filter', 'trail': false}}"
    context['visParameters'] = coll.vis_parameters

    return context

"""
COLLECTION GROUPS
"""
class CollectionGroupCreateView(CreateView):
  form_class = CollectionGroupModelForm
  template_name = 'collection/collection_group_create.html'
  queryset = CollectionGroup.objects.all()

  #
  def get_form_kwargs(self, **kwargs):
    kwargs = super(CollectionGroupCreateView, self).get_form_kwargs()
    # print('kwargs', kwargs)
    print('GET in CollectionGroupCreateView()', self.request.GET)
    return kwargs

  def get_success_url(self):
    cgid = self.kwargs.get("id")
    action = self.kwargs.get("action")
    # def get_success_url(self):
    #         return reverse('doc_aide:prescription_detail', kwargs={'pk': self.object.pk})
    return reverse('collection:collection-group-update', kwargs={'id':self.object.id})
    # return redirect('collections/groups/'+str(cgid)+'/update')
    # return '/accounts/profile/'

  def form_invalid(self, form):
    print('form invalid...', form.errors.as_data())
    context = {'form': form}
    return self.render_to_response(context=context)

  def form_valid(self, form):
    context = {}
    if form.is_valid():
      print('form is valid, cleaned_data', form.cleaned_data)
      self.object = form.save()
      return HttpResponseRedirect(self.get_success_url())
    # else:
    #   print('form not valid', form.errors)
    #   context['errors'] = form.errors
    # return super().form_valid(form)

  def get_context_data(self, *args, **kwargs):
    context = super(CollectionGroupCreateView, self).get_context_data(*args, **kwargs)
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY
    # print('args',args,kwargs)
    context['action'] = 'create'
    # context['referrer'] = self.request.POST.get('referrer')
    return context

class CollectionGroupDetailView(DetailView):
  model = CollectionGroup
  template_name = 'collection/collection_group_detail.html'

  def get_success_url(self):
    pid = self.kwargs.get("id")
    # print('messages:', messages.get_messages(self.kwargs))
    return '/collection/' + str(pid) + '/detail'

  def get_object(self):
    id_ = self.kwargs.get("id")
    return get_object_or_404(CollectionGroup, id=id_)

  def get_context_data(self, *args, **kwargs):
    context = super(CollectionGroupDetailView, self).get_context_data(*args, **kwargs)
    context['mbtokenkg'] = settings.MAPBOX_TOKEN_KG
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY

    print('CollectionGroupDetailView get_context_data() kwargs:', self.kwargs)
    print('CollectionGroupDetailView get_context_data() request.user', self.request.user)
    cg = get_object_or_404(CollectionGroup, pk=self.kwargs.get("id"))
    me = self.request.user
    # if Collection has a group, it is submitted
    context['submitted'] = Collection.objects.filter(group=cg.id).count()
    context['message'] = 'CollectionGroupDetailView() loud and clear'
    context['links'] = Link.objects.filter(collection_group_id=self.get_object())
    context['beta_or_better'] = True if self.request.user.groups.filter(name__in=['beta', 'admins']).exists() else False

    return context

class CollectionGroupDeleteView(DeleteView):
  template_name = 'collection/collection_group_delete.html'

  def get_object(self):
    id_ = self.kwargs.get("id")
    return get_object_or_404(CollectionGroup, id=id_)

  def get_success_url(self):
    return reverse('accounts:profile')

"""
  update (edit); uses same template as create;
  context['action'] governs template display
"""
class CollectionGroupUpdateView(UpdateView):
  form_class = CollectionGroupModelForm
  template_name = 'collection/collection_group_create.html'

  def get_form_kwargs(self, **kwargs):
    kwargs = super(CollectionGroupUpdateView, self).get_form_kwargs()
    return kwargs

  def get_object(self):
    id_ = self.kwargs.get("id")
    return get_object_or_404(CollectionGroup, id=id_)

  def form_valid(self, form):
    id_ = self.kwargs.get("id")
    if form.is_valid():
      print('form.cleaned_data', form.cleaned_data)
      obj = form.save(commit=False)
      obj.save()
      return redirect('/collections/group/' + str(id_) + '/update')
    else:
      print('form not valid', form.errors)
    return super().form_valid(form)

  def get_context_data(self, *args, **kwargs):
    print('CollectionGroupUpdateView() kwargs', self.kwargs)
    context = super(CollectionGroupUpdateView, self).get_context_data(*args, **kwargs)
    cg= self.get_object()
    members = [m.user for m in cg.members.all()]
    context['action'] = 'update'
    context['members'] = members
    context['collections'] = Collection.objects.filter(group=cg.id)
    context['links'] = Link.objects.filter(collection_group_id = self.get_object())
    return context

class CollectionGroupGalleryView(ListView):
  redirect_field_name = 'redirect_to'

  context_object_name = 'collections'
  template_name = 'collection/collection_group_gallery.html'
  model = Collection

  def get_object(self):
    id_ = self.kwargs.get("id")
    return get_object_or_404(CollectionGroup, id=id_)

  def get_queryset(self):
    # original qs
    qs = super().get_queryset()
    return qs
    # return qs.filter(public = True).order_by('core','title')

  def get_context_data(self, *args, **kwargs):
    context = super(CollectionGroupGalleryView, self).get_context_data(*args, **kwargs)
    cg = CollectionGroup.objects.get(id=self.kwargs.get("id"))

    # public datasets available as dataset_list
    # public collections
    context['group'] = self.get_object()
    # context['collections'] = cg.collections.all()
    context['collections'] = Collection.objects.filter(
      group=cg.id,status__in=['reviewed','published']).order_by('submit_date')
    # context['viewable'] = ['uploaded','inserted','reconciling','review_hits','reviewed','review_whg','indexed']

    context['beta_or_better'] = True if self.request.user.groups.filter(name__in=['beta', 'admins']).exists() else False
    return context


""" DATASET COLLECTIONS """
""" datasets only collection
    uses ds_collection_build.html
"""
class DatasetCollectionCreateView(LoginRequiredMixin, CreateView):
  # print('hit DatasetCollectionCreateView()')
  form_class = CollectionModelForm
  # TODO: new ds collection builder
  template_name = 'collection/ds_collection_build.html'
  queryset = Collection.objects.all()

  def get_success_url(self):
    Log.objects.create(
      # category, logtype, "timestamp", subtype, note, dataset_id, user_id
      category = 'collection',
      logtype = 'create',
      note = 'created collection id: '+str(self.object.id),
      user_id = self.request.user.id
    )
    return reverse('dashboard')
  #
  def get_form_kwargs(self, **kwargs):
    kwargs = super(DatasetCollectionCreateView, self).get_form_kwargs()
    return kwargs

  def form_invalid(self,form):
    print('form invalid...',form.errors.as_data())
    context = {'form': form}
    return self.render_to_response(context=context)

  def form_valid(self, form):
    context={}
    print('form is valid, cleaned_data',form.cleaned_data)
    return super().form_valid(form)

  def get_context_data(self, *args, **kwargs):
    user = self.request.user
    context = super(DatasetCollectionCreateView, self).get_context_data(*args, **kwargs)
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY
    context['whgteam'] = User.objects.filter(groups__name='whg_team')

    datasets = []
    # owners create collections from their datasets
    ds_select = [obj for obj in Dataset.objects.all().order_by('title').exclude(title__startswith='(stub)')
                 if user in obj.owners or user in obj.collaborators or user.is_superuser]

    context['action'] = 'create'
    context['ds_select'] = ds_select
    context['coll_dsset'] = datasets

    return context

""" update dataset collection
    uses ds_collection_build.html
"""
class DatasetCollectionUpdateView(UpdateView):
  form_class = CollectionModelForm
  template_name = 'collection/ds_collection_build.html'

  def get_object(self):
    id_ = self.kwargs.get("id")
    return get_object_or_404(Collection, id=id_)

  def get_success_url(self):
    id_ = self.kwargs.get("id")
    return '/collections/'+str(id_)+'/browse_ds'

  def form_valid(self, form):
    if form.is_valid():
      print(form.cleaned_data)
      obj = form.save(commit=False)
      obj.save()
      Log.objects.create(
        # category, logtype, "timestamp", subtype, note, dataset_id, user_id
        category = 'collection',
        logtype = 'update',
        note = 'collection id: '+ str(obj.id) + ' by '+ self.request.user.name,
        user_id = self.request.user.id
      )
    else:
      print('form not valid', form.errors)
    return super().form_valid(form)

  def get_context_data(self, *args, **kwargs):
    context = super(DatasetCollectionUpdateView, self).get_context_data(*args, **kwargs)
    user = self.request.user
    _id = self.kwargs.get("id")
    print('DatasetCollectionUpdateView() kwargs', self.kwargs)
    coll = self.get_object()
    datasets = coll.datasets.all()

    # populates dropdown
    ds_select = [obj for obj in Dataset.objects.all().order_by('title').exclude(title__startswith='(stub)')
                 if user in obj.owners or user in obj.collaborators or user.is_superuser]

    context['action'] = 'update'
    context['ds_select'] = ds_select
    context['coll_dsset'] = datasets
    context['created'] = self.object.created.strftime("%Y-%m-%d")

    context['owner'] = True if user == coll.owner else False # actual owner
    context['is_owner'] = True if user in self.object.owners else False # owner or co-owner
    context['is_member'] = True if user in coll.owners or user in coll.collaborators else False
    context['whgteam'] = True if user.groups.filter(name__in=['whg_team','editorial']).exists() else False
    context['collabs'] = CollectionUser.objects.filter(collection=coll.id)

    # TODO: deprecated?
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY

    return context

""" public collection view, datasets, bboxes on a map """
class DatasetCollectionSummaryView(DetailView):
  template_name = 'collection/ds_collection_summary.html'

  model = Collection

  def get_context_data(self, **kwargs):
    context = super(DatasetCollectionSummaryView, self).get_context_data(**kwargs)
    id_ = self.kwargs.get("pk")
    print('CollectionDetailView(), kwargs',self, self.kwargs)

    datasets = self.object.datasets.all()

    # gather bounding boxes
    bboxes = [ds.bounds for ds in datasets]

    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY
    context['whgteam'] = User.objects.filter(groups__name='whg_team')

    context['ds_list'] = datasets
    context['links'] = Link.objects.filter(collection=id_)
    context['bboxes'] = bboxes
    return context

""" browse collection dataset places
    same for owner(s) and public
"""
class DatasetCollectionBrowseView(DetailView):
  login_url = '/accounts/login/'
  redirect_field_name = 'redirect_to'

  model = Collection
  template_name = 'collection/ds_collection_browse.html'

  def get_success_url(self):
    id_ = self.kwargs.get("id")
    return '/collections/'+str(id_)+'/places'

  def get_object(self):
    id_ = self.kwargs.get("id")
    return get_object_or_404(Collection, id=id_)

  def get_context_data(self, *args, **kwargs):
    context = super(DatasetCollectionBrowseView, self).get_context_data(*args, **kwargs)
    print('DatasetCollectionBrowseView get_context_data() kwargs:',self.kwargs)
    print('DatasetCollectionBrowseView get_context_data() request.user',self.request.user)

    context['mbtokenkg'] = settings.MAPBOX_TOKEN_KG
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY
    context['media_url'] = settings.MEDIA_URL

    id_ = self.kwargs.get("id")
    # compute bounding boxes

    coll = get_object_or_404(Collection, id=id_)
    # "geotypes":ds.geotypes,
    # datasets = [{"id":ds.id,"label":ds.label,"title":ds.title} for ds in coll.ds_list]
                 # "bbox": ds.bounds } for ds in coll.datasets.all()]
    #bboxes = [{"id":ds['id'], "geometry":ds['bounds']} for ds in datasets]

    # sg 21-Dec-2023: These 2 lines appear to be redundant:
    placeset = coll.places.all()
    context['places'] = placeset

    context['ds_list'] = coll.ds_list
    context['links'] = Link.objects.filter(collection=id_)
    context['updates'] = {}
    context['coll'] = coll
    context['beta_or_better'] = True if self.request.user.groups.filter(name__in=['beta', 'admins']).exists() else False

    return context

""" browse collection collections
    w/student section?
"""
class CollectionGalleryView(ListView):
  redirect_field_name = 'redirect_to'

  context_object_name = 'collections'
  template_name = 'collection/collection_gallery.html'
  model = Collection

  def get_queryset(self):
    qs = super().get_queryset()
    return qs.filter(public = True).order_by('title')

  def get_context_data(self, *args, **kwargs):
    context = super(CollectionGalleryView, self).get_context_data(*args, **kwargs)
    # public collections
    # context['group'] = self.get_object()
    context['place_collections'] = Collection.objects.filter(collection_class='place', public=True)
    context['dataset_collections'] = Collection.objects.filter(collection_class='dataset', public=True)
    context['student_collections'] = Collection.objects.filter(nominated=True)

    context['beta_or_better'] = True if self.request.user.groups.filter(name__in=['beta', 'admins']).exists() else False
    return context

class CollectionDeleteView(DeleteView):
  template_name = 'collection/collection_delete.html'

  def get_object(self):
    id_ = self.kwargs.get("id")
    return get_object_or_404(Collection, id=id_)

  def get_success_url(self):
    return reverse('dashboard')
