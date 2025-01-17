// /whg/webpack/portal.js

import throttle from 'lodash/throttle';
import { attributionString, deepCopy, geomsGeoJSON } from './utilities';
import Dateline from './dateline';
import { popupFeatureHTML } from './getPlace.js';
import { init_collection_listeners } from './collections.js';
import { add_to_collection } from './collections.js';

import '../css/mapAndTableMirrored.css';
import '../css/dateline.css';
import '../css/portal.css';

const payload = JSON.parse($('#payload_data').text());

let checked_cards = [];

let mapParameters = {
	maxZoom: 17,
    style: ['whg-basic-light', 'whg-basic-dark'],
    basemap: ['natural-earth-1-landcover', 'natural-earth-2-landcover', 'natural-earth-hypsometric-noshade'],
    terrainControl: true,
	temporalControl: temporal
}
let mappy = new whg_maplibre.Map(mapParameters);

const noSources = $('<div>').html('<i>None - please adjust time slider.</i>').hide();

let featureCollection;
let relatedFeatureCollection;
let nearbyFeatureCollection;
let showingRelated = false;

let nearPlacePopup = new whg_maplibre.Popup({
	closeButton: false,
	})
.addTo(mappy);
$(nearPlacePopup.getElement()).hide();

function waitMapLoad() {
    return new Promise((resolve) => {
        mappy.on('load', () => {
            console.log('Map loaded.');

			const controlContainer = document.querySelector('.maplibregl-control-container');
			controlContainer.setAttribute('id', 'mapControls');
			controlContainer.classList.add('item');

			const mapOverlays = document.createElement('div');
			mapOverlays.id = 'mapOverlays';
			mappy.getContainer().appendChild(mapOverlays);

			['left', 'centre', 'right'].forEach(function(side) {
				const column = document.createElement('div');
				column.classList.add('column', side);
				mapOverlays.appendChild(column);
				const overlays = document.querySelectorAll('.overlay.' + side);
				overlays.forEach(function(overlay) {
					if (overlay.id == 'map') {
						column.appendChild(controlContainer);
						overlay.classList.remove('overlay','left','right');
					}
					else {
						column.appendChild(overlay);
						overlay.classList.add('item');
					}
				})
			});

            mappy
			.newSource('nearbyPlaces') // Add empty source
			.newLayerset('nearbyPlaces', 'nearbyPlaces', 'nearby-places');

            mappy
			.newSource('places') // Add empty source
			.newLayerset('places')
			.addFilter(['!=', 'outOfDateRange', true]);

			$('#map_options').append(createNearbyPlacesControl());

			const dateRangeChanged = throttle(() => { // Uses imported lodash function
			    filterSources();
			}, 300);

			if (!!mapParameters.temporalControl) {
				let datelineContainer = document.createElement('div');
				datelineContainer.id = 'dateline';
				document.getElementById('mapControls').appendChild(datelineContainer);
				window.dateline = new Dateline({
					...mapParameters.temporalControl,
					onChange: dateRangeChanged
				});
			};
			$(window.dateline.button).on('click', dateRangeChanged);

			mappy.on('mousemove', function(e) {
				const features = mappy.queryRenderedFeatures(e.point);

				function clearHighlights() {
					if (mappy.highlights.length > 0) {
						mappy.getCanvas().style.cursor = 'grab';
						mappy.clearHighlights();
						$('.source-box').removeClass('highlight');
					}
				}

				if (!showingRelated) {
					if (features.length > 0) {
						clearHighlights();
						features.forEach(feature => {
							if (feature.layer.id.startsWith('places_')) {
								mappy.highlight(feature);
								$('.source-box').eq(feature.id).addClass('highlight');
							}
						});
						features.forEach(feature => { // Check nearbyPlaces
							if (feature.layer.id.startsWith('nearbyPlaces_')) {
								nearPlacePopup
								.setLngLat(e.lngLat)
								.setHTML(popupFeatureHTML(feature, false)); // second parameter indicates clickability								
							}
						$(nearPlacePopup.getElement()).show();
						});
						if (mappy.highlights.length > 0) {
							mappy.getCanvas().style.cursor = 'pointer';
						}

					} else {
						clearHighlights();
						$(nearPlacePopup.getElement()).hide();
					}
				}

			});

			mappy.on('click', function() {
				if (!showingRelated && mappy.highlights.length > 0) {
					console.log(mappy.highlights);
					mappy.fitViewport( bbox( geomsGeoJSON(mappy.highlights) ) );
				}
			});

			mappy.getContainer().style.opacity = 1;

            resolve();
        });
    });
}

function waitDocumentReady() {
    return new Promise((resolve) => {
        $(document).ready(() => {
            // Get the 'add to collection' link and the 'addtocoll_popup' div
            const link = document.getElementById('addchecked');
            const popup = document.getElementById('addtocoll_popup');

			let checked_cards =[]

			// Add an event listener for the radio buttons
			// document.querySelectorAll('input[name="r_anno"]').forEach(radio => {
			// 	radio.addEventListener('click', function() {
			// 		// Add the data-id value of the .pop-link <a> tag to the checked_cards array
			// 		const pid = this.closest('.source-box').querySelector('.pop-link').dataset.id;
			// 		checked_cards.push(pid);
			//
			// 		// Unhide the #addtocoll span
			// 		document.getElementById('addtocoll').style.display = 'block';
			// 	});
			// });

			document.querySelectorAll('input[name="r_anno"]').forEach(radio => {
					radio.addEventListener('click', function() {
							// Add the data-id value of the radio input to the checked_cards array
							const pid = $(this).data('id');
							checked_cards = [pid];
							console.log('checked_cards', checked_cards);
							// Unhide the #addtocoll span
							document.getElementById('addtocoll').style.display = 'block';
					});
			});
			// Add an event listener for the #addchecked link
			document.getElementById('addchecked').addEventListener('click', function(event) {
				event.preventDefault();
				let popup = document.getElementById('addtocoll_popup');
				// Unhide the #addtocoll_popup div
				popup.style.top = '40px';
                popup.style.left = '468px';
				popup.style.display = 'block';

			});

			// Add an event listener for the .a_addtocoll links
			document.querySelectorAll('.a_addtocoll').forEach(link => {
				link.addEventListener('click', function(event) {
					event.preventDefault();

					// Call the add_to_collection function with the appropriate arguments
					const coll = this.getAttribute('ref');
					add_to_collection(coll, checked_cards);

					// Clear the checked_cards array
					checked_cards = [];
				});
			});
            resolve();
        });
    });
}

Promise.all([waitMapLoad(), waitDocumentReady()])
    .then(() => {

    	const collectionList = $('#collection_list');
    	const ul = $('<ul>').addClass('coll-list');
    	payload.forEach(dataset => {
		  	if (dataset.collections.length > 0) {
				  dataset.collections.forEach(collection => {
			            let listItem = '';
			            if (collection.class === 'place') {
			                listItem = `
			                    <a href="${ collection.url }" target="_blank">
			                        <b>${ collection.title.trim() }</b>
			                    </a>, a collection of <sr>${ collection.count }</sr> places.
			                    <span class="showing"><p>${ collection.description }</p></span>
			                    [<a href="javascript:void(0);" data-id="${ collection.id }" class="show-collection"><span>show</span><span class="showing">hide</span></a>]
			                `;
			            } else {
			                listItem = `
			                    <a href="${ collection.url }" target="_blank">
			                        <b>${title}</b>
			                    </a>, a collection of all <sr>${ collection.count }</sr> places in datasets
			                `;
			            }
			            ul.append($('<li>').html(listItem));
				  });
			}
		});
		if (ul.find('li').length > 0) {
		    collectionList.append(ul);
		}
		else {
			collectionList.html('<i>None yet</i>');
		}

		$('#sources').append(noSources);

		featureCollection = geomsGeoJSON(payload);
		console.log(featureCollection);
		mappy.getSource('places').setData(featureCollection);
		// Do not use fitBounds or flyTo due to padding bug in MapLibre/Maptiler
		mappy.fitViewport( bbox(featureCollection) );

	  	var min = Math.min.apply(null, allts.map(function(row) {
	  		return Math.min.apply(Math, row);
	  	}));
	  	var max = Math.max.apply(null, allts.map(function(row) {
	  		return Math.max.apply(Math, row);
	  	}));
	  	let minmax = [min, max]
	  	// feed to #histogram
	  	histogram_data(allts, minmax)

	  	$('.source-box')
	  	.on('mousemove', function() {
			  if (!showingRelated) {
				  $(this)
				  .prop('title', 'Click to zoom on map.')
				  .addClass('highlight');
				  const index = $(this).index() - 1;
				  mappy.setFeatureState({source: 'places', id: index}, { highlight: true });
			  }
		})
	  	.on('mouseleave', function() {
			  if (!showingRelated) {
				  $(this)
				  .prop('title', '')
				  .removeClass('highlight');
				  const index = $(this).index() - 1;
				  mappy.setFeatureState({source: 'places', id: index}, { highlight: false });
				  mappy.fitViewport( bbox( featureCollection ) );
			  }
		})
	  	.on('click', function() {
			  if (!showingRelated) {
				  $(this)
				  .prop('title', '')
				  const index = $(this).index() - 1;
				  mappy.fitViewport( bbox( featureCollection.features[index].geometry ) );
			  }
		})

	  	// Show/Hide related Collection
	  	$(".show-collection").click(function(e) {
	  		e.preventDefault();
	  		const parentItem = $(this).parent('li');
	  		parentItem.toggleClass('showing');
	  		if (parentItem.hasClass('showing')) {
			  	$.get("/search/collgeom", {
			  			coll_id: $(this).data('id')
			  		},
			  		function(collgeom) {
						relatedFeatureCollection = collgeom;
			  			console.log('coll_places', relatedFeatureCollection);
						mappy.getSource('places').setData(relatedFeatureCollection);
						mappy.fitViewport( bbox(relatedFeatureCollection) );
			  		});
			  	showingRelated = true;
			}
			else {
				mappy.getSource('places').setData(featureCollection);
				mappy.fitViewport( bbox(featureCollection) );
				showingRelated = false;
			}
	  	})

        document.querySelectorAll('.toggle-link').forEach(link => {
            link.addEventListener('click', function(event) {
                toggleVariants(event, this);
            });
        });

		new ClipboardJS('#permalinkButton', {
		    text: function() {
		      return window.location.href;
		    }
	  	})
		.on('success', function(e) {
		    e.clearSelection();
		    const tooltip = bootstrap.Tooltip.getInstance(e.trigger);
		    tooltip.setContent({ '.tooltip-inner': 'Permalink copied to clipboard successfully!' });
		    console.log('tooltip',tooltip);
		    setTimeout(function() { // Hide the tooltip after 2 seconds
		        tooltip.hide();
		    	tooltip.setContent({ '.tooltip-inner': tooltip._config.title }) // Restore original text
		    }, 2000);
		})
		.on('error', function(e) {
		    console.error('Failed to copy:', e.trigger);
		});
        
    })
    .catch(error => console.error("An error occurred:", error));

function filterSources() {
	console.log(`Filter dates: ${window.dateline.fromValue} - ${window.dateline.toValue} (includeUndated: ${window.dateline.includeUndated})`);
	function inDateRange(source) {
		if (!window.dateline.open) return true;
        const timespans = source.timespans;
        if (timespans.length > 0) {
		    return !timespans.every(timespan => {
		        return timespan[1] < window.dateline.fromValue || timespan[0] > window.dateline.toValue;
		    });
        } else {
            return window.dateline.includeUndated;
        }
    }
	featureCollection.features.forEach((feature, index) => {
		const outOfDateRange = !inDateRange(feature.properties)
		feature.properties['outOfDateRange'] = outOfDateRange;
		$('.source-box').eq(index).toggle(!outOfDateRange);
	});
	mappy.getSource('places').setData(featureCollection);
	noSources.toggle($('.source-box:visible').length == 0);
}

function range(start, stop, step) {
	var a = [start],
		b = start;
	while (b < stop) {
		a.push(b += step || 1);
	}
	return a;
}

function intersects(a, b) {
	let min = (a[0] < b[0] ? a : b)
	let max = (min == a ? b : a)
	return !(min[1] < max[1])
}

function histogram_data(intervals, minmax) {
	let step = Number(((minmax[1] - minmax[0]) / 200))
	let bins = range(minmax[0], minmax[1], step)
	let hist_array = Array.apply(null, Array(bins.length)).map(Number.prototype.valueOf, 0);
	let labels = bins.map(function(d) {
		return Math.round(d)
	})
	for (var b = 0; b < bins.length; b++) {
		let bin = Array(bins[b], bins[b + 1])
		for (var i in intervals) {
			if (intersects(bin, intervals[i])) {
				hist_array[b] += 1
			}
		}
	}
	let data = hist_array.map(function(d, i) {
		return {
			"bin": labels[i],
			"count": d
		}
	})

	// visualize it
	histogram(data, labels, minmax)

}

function histogram(data, labels, minmax) {
	// exit if no data
	if (data[0].bin == "Infinity") {
		$("#histogram").html('<i>None yet</i>');
		return;
	}
	data = data.slice(0, 200)
	let curwidth = $("#histogram").width()

	var margin = {
			top: 0,
			right: 10,
			bottom: 0,
			left: 10
		},
		width = 400,
		height = 30,
		padding_h = 20,
		padding_w = 30;

	// set the ranges
	window.xScale = d3.scaleLinear()
		.range([0, width])
	window.yScale = d3.scaleLinear()
		.range([height, 0]);

	xScale.domain(minmax);
	yScale.domain([0, d3.max(data, function(d) {
		return d.count;
	})]);

	// TODO: responsive scaling of svg width
	window.svg_hist = d3.select("#histogram").append("svg")
		.attr("width", '100%')
		.attr("height", height + padding_h)

		.attr('viewBox', '0 0 ' + Math.min(width, height + padding_h) + ' ' + Math.min(width, height + padding_h))
		.attr('preserveAspectRatio', 'xMinYMin')

		.append("g")
		.attr("transform", "translate(" + margin.left + "," + margin.top + ")")

	window.axisB = d3.axisBottom(xScale)
		.tickValues(labels.filter(function(d, i) {
			return !(i % 20)
		}))
		.tickFormat(d3.format("d"));

	var axisL = d3.axisLeft(yScale)

	svg_hist.selectAll(".bar")
		.data(data)
		.enter().append("rect")
		.attr("class", "bar")
		.attr("x", function(d) {
			return xScale(d.bin);
		})
		//.attr("width", function(d) { return xScale(d.x1) - xScale(d.x0) -1 ; })
		.attr("width", 2)
		.attr("y", function(d) {
			return yScale(d.count);
		})
		.attr("height", function(d) {
			return height - yScale(d.count);
		});

	var xAxis = svg_hist.append("g")
		.attr("id", "xaxis")
		.attr("transform", "translate(0," + height + ")")
		.call(axisB)
}

function nearbyPlaces() {
	if ( $('#nearby_places').prop('checked') ) {
        const center = mappy.getCenter();
        const radius = $('#radiusSelect').val();
        const lon = center.lng;
        const lat = center.lat;
        $('button#update_nearby').show();

        fetch(`/api/spatial/?type=nearby&lon=${lon}&lat=${lat}&km=${radius}`)
            .then((response) => {
                if (!response.ok) {
                    throw new Error('Failed to fetch nearby places.');
                }
                return response.json(); // Parse the response JSON
            })
            .then((data) => {
				data.features.forEach((feature, index) => feature.id = index);
                nearbyFeatureCollection = data; // Set the global variable
                console.log(nearbyFeatureCollection);
                mappy.getSource('nearbyPlaces').setData(nearbyFeatureCollection);
				$('button#update_nearby').html(`<span class="strong-red">${nearbyFeatureCollection.features.length}</span> Update`);
				if (!showingRelated && nearbyFeatureCollection.features.length > 0) {
					mappy.fitViewport( bbox( nearbyFeatureCollection ) );
				}
            })
            .catch((error) => {
                console.error(error);
            });

	}
	else {
		mappy.clearSource('nearbyPlaces');
        $('button#update_nearby').hide();
	}
}

function createNearbyPlacesControl() {
    const $nearbyPlacesControl = $('<div>').addClass('option-block');
    $('<p>').addClass('strong-red heading').text('Nearby Places').appendTo($nearbyPlacesControl);
    const $itemDiv = $('<div>').addClass('geoLayer-choice');
	const $checkboxItem = $('<input>')
        .attr('id', 'nearby_places')
        .attr('type', 'checkbox')
        //.attr('disabled', 'disabled')
        .on('change', nearbyPlaces);
    const $label = $(`<label for = 'nearby_places'>`).text('Show');
    $itemDiv.append($checkboxItem, $label);

    const $button = $('<button>')
    	.attr('id', 'update_nearby')
    	.attr('title', 'Search again - based on map center')
    	.html('Update')
    	.on('click', nearbyPlaces)
    	.hide();

    const $radiusLabel = $(`<label for = 'radiusSelect'>`).text('Radius: ');
    const $select = $('<select>')
    	.attr('title', 'Search radius, based on map center')
    	.attr('id', 'radiusSelect');
    for (let i = 1; i <= 10; i++) {
        const $option = $('<option>')
            .attr('value', i**2)
            .text(`${i**2} km`);
        $select.append($option);
    }
    $select.val(16).on('change', nearbyPlaces);

    $nearbyPlacesControl.append($button, $itemDiv, $radiusLabel, $select);

    return $nearbyPlacesControl;
}
