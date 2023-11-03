// /whg/webpack/areas.js

import datasetLayers from './mapLayerStyles';
import { attributionString, deepCopy } from './utilities';
import { bbox, buffer, convex, flatten, dissolve, combine } from './6.5.0_turf.min.js';
import { /*StyleControl,*/ CustomAttributionControl } from './customMapControls';
import '../css/maplibre-common.css';
import '../css/areas.css';

let style_code;
if (mapParameters.styleFilter.length == 0) {
	style_code = ['DATAVIZ', 'DEFAULT']
} else {
	style_code = mapParameters.styleFilter[0].split(".");
}

maptilersdk.config.apiKey = mapParameters.mapTilerKey;
let mappy = new maptilersdk.Map({
	container: mapParameters.container,
	center: mapParameters.center,
	zoom: mapParameters.zoom,
	minZoom: mapParameters.minZoom,
	maxZoom: mapParameters.maxZoom,
	style: maptilersdk.MapStyle[style_code[0]][style_code[1]],
	attributionControl: false,
	geolocateControl: false,
	navigationControl: true,
	userProperties: true
});

const nullCollection = {
	type: 'FeatureCollection',
	features: []
}
let featureCollection;

let countryGeoJSON;
var draw;
var drawControl;

let hullLayer = {
	'id': 'hull',
	'type': 'fill',
	'source': 'hulls',
	'paint': {
		'fill-color': 'rgba(221,221,221,.3)', // pale-gray,
		'fill-outline-color': 'rgba(0,128,0,.8)', // green,
	}
}

function waitMapLoad() {
	return new Promise((resolve) => {
		mappy.on('load', () => {
			console.log('Map loaded.');

			// Fetch the river and watershed GeoJSON data
			const fetchRiverData = fetch('/datasets/ne_rivers982/places')
			  .then((response) => {
			    if (!response.ok) {
			      throw new Error('Failed to fetch river data');
			    }
			    return response.json();
			  });
			
			const fetchWatershedData = fetch('/datasets/wri_watersheds/places')
			  .then((response) => {
			    if (!response.ok) {
			      throw new Error('Failed to fetch watershed data');
			    }
			    return response.json();
			  });
			
			// Use Promise.all to wait for both fetch operations to complete
			Promise.all([fetchRiverData, fetchWatershedData])
			  .then(([riverGeoJSON, watershedGeoJSON]) => {
				  
			    if (!!riverGeoJSON.features && riverGeoJSON.features.length > 0) {
			    
				    // Add river and watershed sources and layers
					var riverStyle = {
						'line-color': '#336699',
		  				'line-width': 1,
					};
				    mappy.addSource('rivers', {
				      type: 'geojson',
				      data: riverGeoJSON,
				    });
				    mappy.addLayer({
				      id: 'rivers',
				      type: 'line',
				      source: 'rivers',
				      paint: riverStyle,
				    });
					
				}
				else {
					console.log('Empty or invalid riverGeoJSON.');
				}
				  
			    if (!!watershedGeoJSON.features && watershedGeoJSON.features.length > 0) {
			
					var watershedStyle = {
						'fill-color': '#993333',
						'fill-opacity': 0.1,
						'fill-outline-color': '#fff',
					};
				    mappy.addSource('watersheds', {
				      type: 'geojson',
				      data: watershedGeoJSON,
				    });
				    mappy.addLayer({
				      id: 'watersheds',
				      type: 'fill',
				      source: 'watersheds',
				      paint: watershedStyle,
				    });
					
				}
				else {
					console.log('Empty or invalid watershedGeoJSON.');
				}
			
			    // Now that river and watershed sources/layers are added, proceed with adding other sources and layers
			    mappy.addSource('places', {
			      type: 'geojson',
			      data: nullCollection,
			      attribution: attributionString(),
			    });
			
			    datasetLayers.forEach(function (layer) {
			      mappy.addLayer(layer);
			    });
			
			    mappy.addSource('hulls', {
			      type: 'geojson',
			      data: nullCollection,
			    });
			
			    mappy.addLayer(hullLayer);
			  })
			  .catch((error) => {
			    console.error('Error fetching GeoJSON data:', error);
			  });

			addDrawingControl();
			
/*			if (mapParameters.styleFilter.length !== 1) { // This would be a little complicated (but not impossible) to implement due to MapBox drawing layers; styling also required.
				mappy.addControl(new StyleControl(mappy), 'top-right');
			}*/

			mappy.addControl(new CustomAttributionControl({
				compact: true,
				autoClose: mapParameters.controls.attribution.open === false,
			}), 'bottom-right');
			
			/*		
			drawnItems = L.featureGroup().addTo(mappy)
		
			var baseLayers = {
				"OSM": osm,
				"Satellite": satellite
			};
		
			var overlays = {
				"Drawn features": drawnItems,
				"Rivers": rivers,
				"Watersheds": watersheds
			}
		
			layerGroup = L.control.layers(baseLayers, overlays).addTo(mappy);
			baseLayers['OSM'].addTo(mappy)
			//overlays['Rivers'].addTo(mappy)
			*/

			resolve();
		});
	});
}

function waitDocumentReady() {
	return new Promise((resolve) => {
		$(document).ready(() => resolve());
	});
}

Promise.all([waitMapLoad(), waitDocumentReady()])
	.then(() => {

		// area_type = 'ccodes' // default
		$(".textarea").each(function(index) {
			if (["None", "null"].includes($(this).val())) {
				$(this).val('')
			}
		});
		
		let country_url = "/media/data/countries_simplified.json";
		fetch(country_url)
			.then(function(resp) { return resp.json(); })
			.then(function(data) {
				countryGeoJSON = data;
			});
		
		$("#id_geojson")
			.attr("placeholder", "generated from country codes")
			.attr("disabled", true)

		$('#areas_codes .area-link-clear').click(() => {
			map_clear();
		});
		$('#areas_codes .area-link-render').click(() => {
			map_render();
		});

		$('a[data-toggle="tab"]').on('shown.bs.tab', function(e) {
			const target = $(e.target).attr("href") // activated tab
			const area_type = $(e.target).attr("ref") // activated tab
			map_clear();
			// feed area type to hidden input
			$("input[name='type']").val(area_type)
			console.log('tab id:', target);
			// TODO: better refactor 
			if (target == '#areas_codes') {
				drawControl.hide();
				$("#id_geojson").attr("placeholder", "generated from country codes")
			} else if (target == '#areas_draw') {
				drawControl.show();
				$("#id_geojson").attr("placeholder", "generated from drawn shapes")
			}
		});

		map_init();
	})
	.catch(error => console.error("An error occurred:", error));

function addDrawingControl() {

	draw = new MapboxDraw({
		displayControlsDefault: false,
		controls: {
			//point: true,
			//line_string: true,
			polygon: true,
			trash: true
		},
	})
	let drawControlObject = mappy.addControl(draw, 'top-left');
	drawControl = $(drawControlObject._container).find('.maplibregl-ctrl-top-left');
	drawControl.hide();
	const drawControls = document.querySelectorAll(".mapboxgl-ctrl-group.mapboxgl-ctrl");
	drawControls.forEach((elem) => {
		elem.classList.add('maplibregl-ctrl', 'maplibregl-ctrl-group');
	});
	mappy.on('draw.create', updateGeoJSON);
	mappy.on('draw.delete', updateGeoJSON);
	mappy.on('draw.update', updateGeoJSON);

	function updateGeoJSON() {
		var data = draw.getAll();
		$("textarea#id_geojson").val(data.features.length > 0 ? JSON.stringify(data) : '');
	}

}

function map_init() {
	// whether drawn or ccodes, load existing data
	if (action == 'update') {
		// existing - assumes that formGeoJSON is a featureCollection
		areageom = JSON.parse(formGeoJSON);

		// if area was drawn
		if (formType == 'drawn') {
			console.log('was drawn')
			draw.set(formGeoJSON)
			$('a[href="#areas_draw"]').tab('show');
			// disable ccodes tab
			$('a[href="#areas_codes"]').addClass('disabled').css("cursor", "default")

		} else if (formType == 'ccodes') {
			console.log('was ccodes-generated')
			mappy.getSource('places').setData(formGeoJSON);
			// disable draw tab
			$('a[href="#areas_draw"]').addClass('disabled').css("cursor", "default")
		}
		mappy.fitBounds(bbox(formGeoJSON), {
	        padding: 30,
	        duration: 1000,
	    });
	}
}

function map_clear() {
	draw.deleteAll();
	mappy.getSource('places').setData(nullCollection);
	mappy.getSource('hulls').setData(nullCollection);
	$("input#id_ccodes").val(null);
	if (action == "create") {
		$("textarea#id_geojson").val(null);
	}
	$("#buffer_km").val(null);
	mappy.flyTo({
	    center: mapParameters.center,
	    zoom: mapParameters.zoom,
        duration: 1000,
	});
}

function map_render() {
	mappy.getSource('places').setData(nullCollection);
	mappy.getSource('hulls').setData(nullCollection);
	let ccodes = $("input#id_ccodes").val().split(/[,\s|]+/).map(code => code.trim().toUpperCase()).filter(Boolean);
	let cbuffer = $("input#buffer_km").val();
	featureCollection = deepCopy(nullCollection);
	let hullCollection = deepCopy(nullCollection);
	if (ccodes.length > 0) {
		featureCollection.features = countryGeoJSON.features.filter(feature => ccodes.includes(feature.properties.iso));
		if (featureCollection.features.length ==0) {
			alert('No matches found for those country codes.');
			return;
		}
		featureCollection.features.forEach((feature, index) => { 
			feature.id = index;
			if (cbuffer > 0) {
				const bufferedHull = convex(buffer(feature, cbuffer, { units: 'kilometers' }));
        		hullCollection.features.push(bufferedHull);
			} 
		});
		if (cbuffer > 0) {
			hullCollection = combine(dissolve(flatten(hullCollection)));
			mappy.getSource('hulls').setData(hullCollection);
		}
		mappy.getSource('places').setData(featureCollection);
		featureCollection.features.forEach((feature, index) => {
			mappy.setFeatureState({ source: 'places', id: index }, { highlight: true });
        });
	} else {
		alert('Need one or more comma-delimited 2-letter country codes.');
		return;
	}
    let primaryCollection = cbuffer > 0 ? hullCollection : featureCollection;
    $("textarea#id_geojson").val(JSON.stringify(primaryCollection));
	mappy.fitBounds(bbox(primaryCollection), {
        padding: 30,
        duration: 1000,
    });
}

/*
THE FOLLOWING FUNCTIONS ARE AS-YET REDUNDANT AND MIGHT EVENTUALLY BE REMOVED
 */

// ES query to count...retrieve?
function fetchCount(coords) {
	//startMapitSpinner()
	console.log('coords', coords)
	context = {
		"type": "FeatureCollection",
		"features": []
	}
	$.get("/search/context", {
			idx: 'whg',
			extent: coords,
			task: 'count'
		},
		function(data) {
			console.log('this many:', data['count'])
			$("#count_result").html(data['count'])
		});
}

function random_rgba() {
	var o = Math.round,
		ra = Math.random,
		s = 255;
	tup = [o(ra() * s), o(ra() * s), o(ra() * s)]

	const rgbToHex = (r, g, b) => '#' + [r, g, b].map(x => {
		const hex = x.toString(16)
		return hex.length === 1 ? '0' + hex : hex
	}).join('')

	return rgbToHex(tup[0], tup[1], tup[2])
}

function zoomTo(id) {
	mappy.setView(idToFeature[id]._latlng, mappy.getZoom() + 2)
}

function cleanJson(text) {
	z = text.replace(/'/g, '\\"')
	y = z.replace(/point/, 'Point')
	return JSON.parse(JSON.parse(y))
}