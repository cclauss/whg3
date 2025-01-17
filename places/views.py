from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
User = get_user_model()
from django.http import JsonResponse, HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView
from django.db.models import Count

from datetime import datetime
from elasticsearch8 import Elasticsearch
from collections import Counter
import itertools, re
from django.core.serializers import serialize
from urllib.parse import unquote_plus

from collection.models import Collection
from datasets.models import Dataset
from places.models import Place
from places.utils import attribListFromSet

# write review status = 2 (per authority)
def defer_review(request, pid, auth, last):
  print('defer_review() pid, auth, last', pid, auth, last)
  p = get_object_or_404(Place, pk=pid)
  if auth in ['whg','idx']:
    p.review_whg = 2
  elif auth.startswith('wd'):
    p.review_wd = 2
  else:
    p.review_tgn = 2
  p.save()
  referer = request.META.get('HTTP_REFERER')
  base = re.search('^(.*?)review', referer).group(1)
  print('referer',referer)
  print('last:',int(last))
  if '?page' in referer:
    nextpage=int(referer[-1])+1
    if nextpage < int(last):
      # there's a next record/page
      return_url = referer[:-1] + str(nextpage)
    else:
      return_url = base + 'reconcile'
  else:
    # first page, might also be last for pass
    if int(last) > 1:
      return_url = referer + '?page=2'
    else:
      return_url = base + 'reconcile'
  # return to calling page
  return HttpResponseRedirect(return_url)

class SetCurrentResultView(View):
  def post(self, request, *args, **kwargs):
    place_ids = request.POST.getlist('place_ids')
    print('Setting place_ids in session:', place_ids)
    request.session['current_result'] = {'place_ids': place_ids}
    # messages.success(request, 'Place details loaded successfully!')
    return JsonResponse({'status': 'ok'})

class PlacePortalView(TemplateView):
  template_name = 'places/place_portal.html'

  def get_context_data(self, *args, **kwargs):
    context = super(PlacePortalView, self).get_context_data(*args, **kwargs)
    context['mbtokenkg'] = settings.MAPBOX_TOKEN_KG
    context['mbtokenwhg'] = settings.MAPBOX_TOKEN_WHG
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY

    me = self.request.user
    if not me.is_anonymous:
      if me.groups.filter(name='whg_admins').exists():
        context['my_collections'] = Collection.objects.filter(collection_class='place')
      else:
        context['my_collections'] = Collection.objects.filter(owner=me, collection_class='place')

    context['payload'] = [] # parent and children if any
    context['traces'] = [] #
    context['allts'] = []

    context['core'] = ['ne_countries','ne_rivers982','ne_mountains','wri_lakes']
    
    # Extract any whg_id from a permalink URL
    whg_id = kwargs.get('whg_id', '')    
    # Extract any encoded IDs from a permalink URL
    encoded_ids = kwargs.get('encoded_ids', '')
    if whg_id:
        print('Assembling parent and child place_ids')   
        # TO DO - search ES - in the meantime, fall back to the IDs stored in the session variable
        place_ids = self.request.session.get('current_result', {}).get('place_ids', [])
    elif encoded_ids:
        place_ids = list(map(int, encoded_ids.split(',')))
    else:
        # Fall back to the IDs stored in the session variable
        place_ids = self.request.session.get('current_result', {}).get('place_ids', [])

    place_ids = list(map(int, place_ids))
    print('place_ids in portal.js', place_ids)

    if not place_ids:
        messages.error(self.request, "Place IDs are required to view this page")
        raise Http404("Place IDs are required")

    alltitles = set()
    allvariants = []
    try:
      place_ids = [int(pid) for pid in place_ids]
      qs = Place.objects.filter(id__in=place_ids).order_by('-whens__minmax')
      #context['title'] = qs.first().title
      collections = []
      annotations = []
      print('qs', qs)
      print('place_ids', place_ids)
      for place in qs:
        ds = Dataset.objects.get(id=place.dataset.id)
        print('place.title', place.title)
        alltitles.add(place.title)

        # temporally scoped attributes
        names = attribListFromSet('names', place.names.all(), exclude_title=place.title)
        print('names for a place:', names)
        types = attribListFromSet('types', place.types.all())

        # get traces, collections for this attestation
        attest_traces = list(place.traces.all())
        attest_collections = [t.collection for t in attest_traces if t.collection.status == "published"]

        # add to global list
        annotations = annotations + attest_traces
        collections = list(set(collections + attest_collections))

        # collections = Collection.objects.filter(collection_class="place", places__id__in = place_ids).distinct()

        geoms = [geom.jsonb for geom in place.geoms.all()]
        related = [rel.jsonb for rel in place.related.all()]

        # timespans generated upon Place record creation
        # draws from 'when' in names, types, geoms, relations
        # deliver to template in context
        timespans = list(t for t, _ in itertools.groupby(place.timespans)) if place.timespans else []
        context['allts'] += timespans

        collection_records = []
        for collection in attest_collections:
            collection_url = reverse('collection:place-collection-browse', args=[collection.id])
            collection_record = {
                "class": collection.collection_class,
                "id": collection.id,
                "url": collection_url,
                "title": collection.title,
                "description": collection.description,
                "count": collection.places_all.aggregate(place_count=Count('id'))['place_count']
            }
            collection_records.append(collection_record)

        record = {
          # "whg_id": id_,
          "dataset": {"id": ds.id, "label": ds.label,
                      "name": ds.title, "webpage": ds.webpage},
          "place_id": place.id,
          "src_id": place.src_id,
          "purl": ds.uri_base + str(place.id) if 'whgaz' in ds.uri_base else ds.uri_base + place.src_id,
          "title": place.title,
          "ccodes": place.ccodes,
          "names": names,
          "types": types,
          "geom": geoms,
          "related": related,
          "links": [link.jsonb for link in place.links.distinct('jsonb') if
                    not link.jsonb['identifier'].startswith('whg')],
          "descriptions": [descr.jsonb for descr in place.descriptions.all()],
          "depictions": [depict.jsonb for depict in place.depictions.all()],
          "minmax": place.minmax,
          "timespans": timespans,
          "collections": collection_records
        }
        for name in names:
          variant = name.get('label', '')
          if variant != place.title:
            allvariants.append(variant)

        context['payload'].append(record)
    except ValueError:
      messages.error(self.request, "Invalid place ID format")
      raise Http404("Invalid place ID format")

    title_counts = Counter(alltitles)
    variant_counts = Counter(allvariants)

    # Find the two most common titles and variants
    common_titles = [title for title, _ in title_counts.most_common(2)]
    common_variants = [variant for variant, _ in variant_counts.most_common(2)]

    # Construct the portal headword
    portal_headword = common_titles + common_variants
    context['portal_headword'] = "; ".join(portal_headword)+"; ..."
    context['annotations'] = annotations
    context['collections'] = collections

    
    # Calculate initialisation values for temporal control
    
    min_ts = float('inf')
    max_ts = float('-inf')
    
    for t in timespans:
        start, end = t
        min_ts = min(min_ts, start)
        max_ts = max(max_ts, end)
        
    if min_ts == float('inf') or max_ts == float('-inf'):
        min_ts = False
        max_ts = False
        from_value = False
        to_value = False
    else:
        range_percentage = 5
        from_value = min_ts - (range_percentage / 100) * (max_ts - min_ts)
        to_value = max_ts + (range_percentage / 100) * (max_ts - min_ts)
    
    context['min_timespan'] = min_ts
    context['max_timespan'] = max_ts
    context['from_value'] = from_value
    context['to_value'] = to_value

    return context

# class PlacePortalView(DetailView):
#   # template_name = 'places/place_portal.html'
#   template_name = 'places/place_portal_new.html'
#
#   #
#   # given index id (whg_id) returned by typeahead/suggest,
#   # get its db record (a parent);
#   # build array of place_ids (parent + children);
#   # iterate those to build payload;
#   # create add'l context values from set
#   #
#
#   def get_object(self):
#     id_ = self.kwargs.get("id")
#     print('PlacePortalView() args',self.args,'kwargs:',self.kwargs)
#     es = settings.ES_CONN
#     q = {"query":{"bool": {"must": [{"match":{"_id": id_}}]}}}
#     pid=es.search(index='whg',body=q)['hits']['hits'][0]['_source']['place_id']
#     # pid=es.search(index='whg', body=q)['hits']['hits'][0]['_source']['place_id']
#     self.kwargs['pid'] = pid
#     return get_object_or_404(Place, id=pid)
#
#   def get_context_data(self, *args, **kwargs):
#     print('get_context_data kwargs',self.kwargs)
#     context = super(PlacePortalView, self).get_context_data(*args, **kwargs)
#     context['mbtokenkg'] = settings.MAPBOX_TOKEN_KG
#     context['mbtokenwhg'] = settings.MAPBOX_TOKEN_WHG
#     context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
#     context['maptilerkey'] = settings.MAPTILER_KEY
#     es = settings.ES_CONN
#     id_ = self.kwargs.get("id")
#     pid = self.kwargs.get("pid")
#     me = self.request.user
#     place = get_object_or_404(Place, id=pid)
#     if not me.is_anonymous:
#       context['my_collections'] = Collection.objects.filter(owner=me, collection_class='place')
#     context['whg_id'] = id_
#     context['payload'] = [] # parent and children if any
#     context['traces'] = [] #
#     context['allts'] = []
#     # place portal headers gray for records from these
#     context['core'] = ['ne_countries','ne_rivers982','ne_mountains','wri_lakes']
#
#     ids = [pid]
#     # get child record ids from index
#     q = {"query": {"parent_id": {"type": "child","id":id_}}}
#     children = es.search(index='whg', body=q)['hits']
#     for hit in children['hits']:
#       #ids.append(int(hit['_id']))
#       ids.append(int(hit['_source']['place_id']))
#
#     # database records for parent + children into 'payload'
#     qs=Place.objects.filter(id__in=ids).order_by('-whens__minmax')
#     # TODO: better way of arriving at title
#     context['title'] = qs.first().title
#
#     collections = []
#     annotations = []
#     # qs is all attestations for a place in the index
#     for place in qs:
#       ds = Dataset.objects.get(id=place.dataset.id)
#       # ds = get_object_or_404(Dataset,id=place.dataset.id)
#       # temporally scoped attributes
#       names = attribListFromSet('names',place.names.all())
#       types = attribListFromSet('types',place.types.all())
#
#       # collections, not traces 20220425
#       # get traces, collections for this attestation
#       attest_traces = list(place.traces.all())
#       attest_collections = [t.collection for t in attest_traces if t.collection.status == "published"]
#       # add to global list
#       annotations = annotations + attest_traces
#       collections = list(set(collections + attest_collections))
#
#       geoms = [geom.jsonb for geom in place.geoms.all()]
#       related = [rel.jsonb for rel in place.related.all()]
#
#       # timespans generated upon Place record creation
#       # draws from 'when' in names, types, geoms, relations
#       # deliver to template in context
#       timespans = list(t for t,_ in itertools.groupby(place.timespans)) if place.timespans else []
#       context['allts'] += timespans
#
#       record = {
#         "whg_id":id_,
#         "dataset":{"id":ds.id,"label": ds.label,
#                    "name":ds.title,"webpage":ds.webpage},
#         "place_id":place.id,
#         "src_id":place.src_id,
#         "purl":ds.uri_base+str(place.id) if 'whgaz' in ds.uri_base else ds.uri_base+place.src_id,
#         "title":place.title,
#         "ccodes":place.ccodes,
#         "names":names,
#         "types":types,
#         "geoms":geoms,
#         "related":related,
#         "links":[link.jsonb for link in place.links.distinct('jsonb') if not link.jsonb['identifier'].startswith('whg')],
#         "descriptions":[descr.jsonb for descr in place.descriptions.all()],
#         "depictions":[depict.jsonb for depict in place.depictions.all()],
#         "minmax":place.minmax,
#         "timespans":timespans
#       }
#       context['payload'].append(record)
#
#     # collections & trace annotations from all attestations
#     context['collections'] = collections
#     context['annotations'] = annotations
#
#     return context

class PlaceDetailView(DetailView):
  #login_url = '/accounts/login/'
  redirect_field_name = 'redirect_to'
  
  model = Place
  template_name = 'places/place_detail.html'

  
  def get_success_url(self):
    pid = self.kwargs.get("id")
    #user = self.request.user
    #print('messages:', messages.get_messages(self.kwargs))
    return '/places/'+str(pid)+'/detail'

  def get_object(self):
    pid = self.kwargs.get("id")
    return get_object_or_404(Place, id=pid)
  
  def get_context_data(self, *args, **kwargs):
    context = super(PlaceDetailView, self).get_context_data(*args, **kwargs)
    context['mbtokenkg'] = settings.MAPBOX_TOKEN_KG
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY

    print('PlaceDetailView get_context_data() kwargs:',self.kwargs)
    print('PlaceDetailView get_context_data() request.user',self.request.user)
    place = get_object_or_404(Place, pk= self.kwargs.get("id"))
    ds = place.dataset
    me = self.request.user
    #placeset = Place.objects.filter(dataset=ds.label
    
    context['timespans'] = {'ts':place.timespans or None}
    context['minmax'] = {'mm':place.minmax or None}
    context['dataset'] = ds
    context['beta_or_better'] = True if self.request.user.groups.filter(name__in=['beta', 'admins']).exists() else False

    return context

# TODO:  tgn query very slow
class PlaceModalView(DetailView):
  model = Place

  template_name = 'places/place_modal.html'
  redirect_field_name = 'redirect_to'
    
  def get_success_url(self):
    pid = self.kwargs.get("id")
    #user = self.request.user
    return '/places/'+str(pid)+'/modal'

  def get_object(self):
    pid = self.kwargs.get("id")
    return get_object_or_404(Place, id=pid)
  
  def get_context_data(self, *args, **kwargs):
    context = super(PlaceModalView, self).get_context_data(*args, **kwargs)
    context['mbtokenkg'] = settings.MAPBOX_TOKEN_KG
    context['mbtoken'] = settings.MAPBOX_TOKEN_WHG
    context['maptilerkey'] = settings.MAPTILER_KEY

    print('PlaceModalView get_context_data() kwargs:',self.kwargs)
    print('PlaceModalView get_context_data() request.user',self.request.user)
    place = get_object_or_404(Place, pk=self.kwargs.get("id"))
    ds = place.dataset
    dsobj = {"id":ds.id, "label":ds.label, "uri_base":ds.uri_base,
             "title":ds.title, "webpage":ds.webpage, 
             "minmax":None if ds.core else ds.minmax, 
             "creator":ds.creator, "last_modified":ds.last_modified_text} 
    #geomids = [geom.jsonb['properties']['id'] for geom in place.geoms.all()]
    #context['geoms'] = geoms
    context['dataset'] = dsobj
    context['beta_or_better'] = True if self.request.user.groups.filter(name__in=['beta', 'admins']).exists() else False

    return context

  # //
  # given place_id (pid), return abbreviated place_detail
  # //

class PlaceFullView(PlacePortalView):
  def render_to_response(self, context, **response_kwargs):
    return JsonResponse(context, **response_kwargs)

""" DEPRECATED """
# TODO: retire this trace implementation (replaced by collections)
# def mm_trace(tsarr):
#   if tsarr==[]:
#     return ''
#   else:
#     #print('mm_trace() tsarr',tsarr)
#     # TODO: not only simple years here; sorts string years?
#     starts = sorted( [t['start'] for t in tsarr] )
#     ends = sorted( [t['end'] for t in tsarr] )
#     mm = [min(starts), max(ends)]
#     mm = sorted(list(set([min(starts), max(ends)])))
#     return '('+str(mm[0])+('/'+str(mm[1]) if len(mm)>1 else '')+')'
#
# # get traces for this index parent and its children
# #print('ids',ids)
# qt = {"query": {"bool": {"must": [  {"terms":{"body.place_id": ids }}]}}}
# trace_hits = es.search(index='traces', doc_type='trace', body=qt)['hits']['hits']
# # for each hit, get target and aggregate body relation/when
# for h in trace_hits:
#   # filter bodies for place_id
#   bods=[b for b in h['_source']['body'] if b['place_id'] in ids]
#   bod = {
#     "id": bods[0]['id'],
#     "title": bods[0]['title'],
#     "place_id": bods[0]['place_id'],
#     "relations": [x['relations'][0]['relation'] +' '+mm_trace(x['relations'][0]['when']) for x in bods]
#   }
# context['traces'].append({
#   'trace_id':h['_id'],
#   'target':h['_source']['target'][0] if type(h['_source']['target']) == list else h['_source']['target'],
#   'body': bod,
#   'bodycount':len(h['_source']['body'])
# })



