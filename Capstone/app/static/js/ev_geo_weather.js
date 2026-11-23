/* ============================================================
   EV ChargeNet — Free Public API Interactive Widgets
   Handles:
     - Nominatim explicit-submit geocoding & reverse geocoding
     - OSRM driving route polyline & directions on Leaflet
     - Nearby charging stations search
     - Open-Meteo weather & 12h forecast card
     - India Postal PIN code directory lookup (1-to-many safe)
   ============================================================ */

(function () {
  "use strict";

  const registeredMaps = {};
  let activeRouteLayers = [];
  let activeOriginMarker = null;
  let lastOrigin = null;
  let reversePickEnabled = false;

  function esc(val) {
    return String(val == null ? "" : val)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function registerLeafletHook() {
    if (typeof window.L === "undefined" || !window.L.Map || window.__evHookInstalled) {
      return;
    }
    window.__evHookInstalled = true;
    window.L.Map.addInitHook(function () {
      const self = this;
      setTimeout(function () {
        const container = self.getContainer && self.getContainer();
        if (container && container.id) {
          registeredMaps[container.id] = self;
          self.on("click", function (ev) {
            if (!reversePickEnabled) return;
            reversePickEnabled = false;
            const pickBtn = document.getElementById("evToggleReversePickBtn");
            if (pickBtn) {
              pickBtn.classList.remove("btn-primary");
              pickBtn.classList.add("btn-secondary");
              pickBtn.textContent = "Pick Pin on Map";
            }
            handleReverseGeocode(ev.latlng.lat, ev.latlng.lng, container.id);
          });
        }
      }, 0);
    });
  }

  function getActiveMap(preferredId) {
    if (preferredId && registeredMaps[preferredId]) {
      return registeredMaps[preferredId];
    }
    const keys = Object.keys(registeredMaps);
    return keys.length ? registeredMaps[keys[0]] : null;
  }

  function clearRouteOverlays(map) {
    activeRouteLayers.forEach(function (layer) {
      try {
        map.removeLayer(layer);
      } catch (_) {}
    });
    activeRouteLayers = [];
    if (activeOriginMarker) {
      try {
        map.removeLayer(activeOriginMarker);
      } catch (_) {}
      activeOriginMarker = null;
    }
  }

  async function handleReverseGeocode(lat, lng, mapId) {
    const statusEl = document.getElementById("evGeoStatusPanel");
    if (statusEl) {
      statusEl.innerHTML = '<span class="text-dim">Reverse geocoding via OpenStreetMap Nominatim...</span>';
    }
    try {
      const resp = await fetch(`/api/geo/reverse?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`);
      const data = await resp.json();
      if (!data.ok) {
        if (statusEl) {
          statusEl.innerHTML = `<span style="color:#f59e0b;">${esc(data.error || "Reverse geocoding failed.")}</span>`;
        }
        return;
      }
      setOriginAndFindNearby(data.latitude, data.longitude, data.display_name, mapId);
      if (statusEl) {
        statusEl.innerHTML = `
          <div><strong>Selected Point:</strong> ${esc(data.display_name)}</div>
          <div class="text-dim" style="font-size:0.78rem; margin-top:2px;">
            Coordinates: ${Number(data.latitude).toFixed(5)}, ${Number(data.longitude).toFixed(5)}
            ${data.postcode ? ` &bull; PIN: ${esc(data.postcode)}` : ""}
            &bull; ${esc(data.attribution)}
          </div>`;
      }
    } catch (err) {
      if (statusEl) {
        statusEl.innerHTML = '<span style="color:#ef4444;">Unable to reach reverse geocoding endpoint.</span>';
      }
    }
  }

  async function setOriginAndFindNearby(lat, lng, label, mapId) {
    lastOrigin = { lat: Number(lat), lng: Number(lng), label: label || "Selected Location" };
    const map = getActiveMap(mapId);
    if (map && typeof window.L !== "undefined") {
      clearRouteOverlays(map);
      activeOriginMarker = window.L.circleMarker([lastOrigin.lat, lastOrigin.lng], {
        radius: 9,
        color: "#38bdf8",
        fillColor: "#0284c7",
        fillOpacity: 0.9,
        weight: 2,
      })
        .addTo(map)
        .bindPopup(`<strong>Origin:</strong> ${esc(lastOrigin.label)}`)
        .openPopup();
      map.setView([lastOrigin.lat, lastOrigin.lng], 12);
    }

    const nearbyEl = document.getElementById("evNearbyResults");
    if (!nearbyEl) return;

    nearbyEl.innerHTML = '<div class="text-dim" style="font-size:0.84rem;">Finding nearby verified stations...</div>';
    try {
      const resp = await fetch(`/api/stations/nearby?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}&radius_km=60`);
      const data = await resp.json();
      if (!data.ok || !data.stations.length) {
        nearbyEl.innerHTML = '<div class="text-dim" style="font-size:0.84rem;">No coordinate-verified stations found within 60 km of that location.</div>';
        return;
      }
      const rows = data.stations.slice(0, 6).map(function (st) {
        return `
          <div style="display:flex; justify-content:space-between; align-items:center; gap:0.75rem; padding:0.55rem 0.7rem; border:1px solid rgba(148,163,184,0.16); border-radius:8px; background:rgba(15,23,42,0.55);">
            <div style="min-width:0;">
              <div style="font-weight:700; font-size:0.88rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                <a href="/stations/${Number(st.station_id)}" style="color:#f8fafc;">${esc(st.station_name)}</a>
              </div>
              <div class="text-dim" style="font-size:0.76rem;">
                ${esc(st.city)} &bull; <strong style="color:#10b981;">${Number(st.distance_km).toFixed(1)} km</strong> away &bull; ${esc(st.connector_types || "CCS2")}
              </div>
            </div>
            <button type="button" class="btn btn-primary btn-sm"
              onclick="window.EVGeoWidget.routeToStation(${Number(st.latitude)}, ${Number(st.longitude)}, '${esc(st.station_name).replace(/'/g, "\\'")}', '${esc(mapId || "")}')">
              Route
            </button>
          </div>`;
      });
      nearbyEl.innerHTML = `<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:0.6rem; margin-top:0.6rem;">${rows.join("")}</div>`;
    } catch (_) {
      nearbyEl.innerHTML = '<div style="color:#ef4444; font-size:0.84rem;">Failed to load nearby stations.</div>';
    }
  }

  async function routeToStation(destLat, destLng, stationName, mapId) {
    if (!lastOrigin) {
      const originInput = document.getElementById("evRouteOriginInput");
      if (originInput && originInput.value.trim().length >= 3) {
        await submitGeocodeSearch(originInput.value.trim(), mapId || "detailMap", false);
      }
    }
    if (!lastOrigin) {
      const box = document.getElementById("evRouteSummaryPanel");
      if (box) {
        box.innerHTML = '<span style="color:#f59e0b;">Search an origin address or click "Use My GPS" first to calculate a driving route.</span>';
      }
      return;
    }

    const summaryEl = document.getElementById("evRouteSummaryPanel");
    if (summaryEl) {
      summaryEl.innerHTML = '<span class="text-dim">Calculating OSRM driving route...</span>';
    }

    try {
      const url = `/api/geo/route?origin_lat=${encodeURIComponent(lastOrigin.lat)}&origin_lng=${encodeURIComponent(lastOrigin.lng)}&dest_lat=${encodeURIComponent(destLat)}&dest_lng=${encodeURIComponent(destLng)}`;
      const resp = await fetch(url);
      const route = await resp.json();
      if (!route.ok) {
        if (summaryEl) {
          summaryEl.innerHTML = `<span style="color:#ef4444;">${esc(route.error || "Route calculation failed.")}</span>`;
        }
        return;
      }

      const map = getActiveMap(mapId);
      if (map && typeof window.L !== "undefined" && route.geometry) {
        clearRouteOverlays(map);
        activeOriginMarker = window.L.circleMarker([lastOrigin.lat, lastOrigin.lng], {
          radius: 8,
          color: "#38bdf8",
          fillColor: "#0284c7",
          fillOpacity: 0.9,
          weight: 2,
        })
          .addTo(map)
          .bindPopup(`<strong>Origin:</strong> ${esc(lastOrigin.label)}`);

        const routeLayer = window.L.geoJSON(route.geometry, {
          style: {
            color: route.fallback_mode ? "#f59e0b" : "#10b981",
            weight: 5,
            opacity: 0.92,
            dashArray: route.fallback_mode ? "8, 6" : null,
          },
        }).addTo(map);
        activeRouteLayers.push(routeLayer);
        try {
          map.fitBounds(routeLayer.getBounds().pad(0.18));
        } catch (_) {}
      }

      if (summaryEl) {
        const stepsHtml = (route.steps || []).slice(0, 8).map(function (st) {
          return `<li style="margin-bottom:0.2rem;">${esc(st.instruction)} <span class="text-dim">(${Number(st.distance_m)} m)</span></li>`;
        }).join("");
        summaryEl.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.5rem;">
            <div>
              <strong>Route to ${esc(stationName || "Charging Station")}:</strong>
              <span style="color:#10b981; font-weight:700; margin-left:0.35rem;">${Number(route.distance_km).toFixed(2)} km</span>
              &bull; <strong>~${Number(route.duration_min)} min</strong>
              ${route.fallback_mode ? '<span class="badge badge-warning" style="margin-left:0.4rem;">Straight-Line Fallback</span>' : ""}
            </div>
            <a href="${esc(route.osm_directions_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm">Open in OpenStreetMap &nearr;</a>
          </div>
          ${stepsHtml ? `<ol style="margin:0.4rem 0 0.4rem 1.25rem; padding:0; font-size:0.82rem; color:#cbd5e1;">${stepsHtml}</ol>` : ""}
          <div class="text-dim" style="font-size:0.74rem;">${esc(route.attribution)}</div>`;
      }
    } catch (_) {
      if (summaryEl) {
        summaryEl.innerHTML = '<span style="color:#ef4444;">Network error while computing route.</span>';
      }
    }
  }

  async function submitGeocodeSearch(query, mapId, showNearby) {
    const statusEl = document.getElementById("evGeoStatusPanel");
    if (!query || query.trim().length < 3) {
      if (statusEl) {
        statusEl.innerHTML = '<span style="color:#f59e0b;">Type at least 3 characters and click Search (explicit lookup avoids excessive API traffic).</span>';
      }
      return null;
    }
    if (statusEl) {
      statusEl.innerHTML = '<span class="text-dim">Looking up address via OpenStreetMap Nominatim...</span>';
    }
    try {
      const resp = await fetch(`/api/geo/search?q=${encodeURIComponent(query.trim())}`);
      const data = await resp.json();
      if (!data.ok || !data.results.length) {
        if (statusEl) {
          statusEl.innerHTML = `<span style="color:#f59e0b;">${esc(data.error || "No matching Indian address found.")}</span>`;
        }
        return null;
      }
      const top = data.results[0];
      if (statusEl) {
        statusEl.innerHTML = `
          <div><strong>Matched Area:</strong> ${esc(top.display_name)}</div>
          <div class="text-dim" style="font-size:0.76rem;">
            ${Number(top.latitude).toFixed(5)}, ${Number(top.longitude).toFixed(5)} &bull; ${esc(data.attribution)}
          </div>`;
      }
      if (showNearby) {
        await setOriginAndFindNearby(top.latitude, top.longitude, top.display_name, mapId);
      } else {
        lastOrigin = { lat: Number(top.latitude), lng: Number(top.longitude), label: top.display_name };
      }
      return top;
    } catch (_) {
      if (statusEl) {
        statusEl.innerHTML = '<span style="color:#ef4444;">Address search service unavailable.</span>';
      }
      return null;
    }
  }

  function useBrowserGps(mapId, destLat, destLng, stationName) {
    const statusEl = document.getElementById("evGeoStatusPanel") || document.getElementById("evRouteSummaryPanel");
    if (!navigator.geolocation) {
      if (statusEl) {
        statusEl.innerHTML = '<span style="color:#f59e0b;">Geolocation is not supported by this browser. Enter an address instead.</span>';
      }
      return;
    }
    if (statusEl) {
      statusEl.innerHTML = '<span class="text-dim">Requesting browser GPS location...</span>';
    }
    navigator.geolocation.getCurrentPosition(
      async function (pos) {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        await setOriginAndFindNearby(lat, lng, "Your Current Location", mapId);
        if (destLat != null && destLng != null) {
          await routeToStation(destLat, destLng, stationName, mapId);
        }
      },
      function () {
        if (statusEl) {
          statusEl.innerHTML = '<span style="color:#f59e0b;">Location permission denied. Type a city or landmark instead.</span>';
        }
      },
      { timeout: 8000 }
    );
  }

  async function loadStationWeather(lat, lng, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (lat == null || lng == null || lat === "" || lng === "") {
      container.innerHTML = '<div class="text-dim" style="font-size:0.86rem;">Weather lookup requires verified station GPS coordinates.</div>';
      return;
    }
    try {
      const resp = await fetch(`/api/weather?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`);
      const data = await resp.json();
      if (!data.ok || !data.current) {
        container.innerHTML = `<div class="text-dim" style="font-size:0.86rem;">${esc(data.error || "Weather telemetry temporarily unavailable.")}</div>`;
        return;
      }
      const c = data.current;
      const slots = (data.hourly_forecast || []).slice(0, 4).map(function (h) {
        return `
          <div style="padding:0.45rem 0.6rem; border-radius:8px; background:rgba(15,23,42,0.55); border:1px solid rgba(148,163,184,0.14); text-align:center;">
            <div class="text-dim" style="font-size:0.74rem;">${esc(h.time)}</div>
            <div style="font-weight:700; font-size:0.95rem; margin:0.15rem 0;">${h.temperature_c != null ? esc(h.temperature_c) + "&deg;C" : "--"}</div>
            <div class="text-dim" style="font-size:0.72rem;"><i class="fa-solid ${esc(h.icon || "fa-cloud")}"></i> ${h.rain_probability_pct != null ? esc(h.rain_probability_pct) + "% rain" : esc(h.condition)}</div>
          </div>`;
      }).join("");

      container.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.75rem;">
          <div style="display:flex; align-items:center; gap:0.85rem;">
            <div style="font-size:1.75rem; color:#38bdf8;"><i class="fa-solid ${esc(c.icon || "fa-cloud-sun")}"></i></div>
            <div>
              <div style="font-size:1.35rem; font-weight:800;">${c.temperature_c != null ? esc(c.temperature_c) + "&deg;C" : "--"} &middot; <span style="font-size:1rem; font-weight:600;">${esc(c.condition)}</span></div>
              <div class="text-dim" style="font-size:0.82rem;">
                Rain Prob: ${c.rain_probability_pct != null ? esc(c.rain_probability_pct) + "%" : "N/A"} &bull;
                Wind: ${c.wind_speed_kmh != null ? esc(c.wind_speed_kmh) + " km/h" : "N/A"} &bull;
                Humidity: ${c.humidity_pct != null ? esc(c.humidity_pct) + "%" : "N/A"}
                ${data.cached ? ' &bull; <span style="color:#10b981;">Cached</span>' : ""}
              </div>
            </div>
          </div>
          <div style="font-size:0.72rem; color:var(--text-dim);">${esc(data.attribution)}</div>
        </div>
        ${slots ? `<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(110px, 1fr)); gap:0.5rem; margin-top:0.85rem;">${slots}</div>` : ""}`;
    } catch (_) {
      container.innerHTML = '<div class="text-dim" style="font-size:0.86rem;">Unable to load Open-Meteo weather telemetry.</div>';
    }
  }

  async function lookupIndianPin(pinInputId, resultBoxId, targetCityInputId) {
    const input = document.getElementById(pinInputId);
    const out = document.getElementById(resultBoxId);
    if (!input || !out) return;
    const pin = (input.value || "").trim();
    if (!/^[1-9][0-9]{5}$/.test(pin)) {
      out.innerHTML = '<div style="color:#f59e0b; font-size:0.82rem;">Enter a valid 6-digit Indian PIN code (first digit 1-9).</div>';
      return;
    }
    out.innerHTML = '<div class="text-dim" style="font-size:0.82rem;">Checking India Post PIN directory...</div>';
    try {
      const resp = await fetch(`/api/pincode/${encodeURIComponent(pin)}`);
      const data = await resp.json();
      if (!data.ok) {
        out.innerHTML = `<div style="color:#f59e0b; font-size:0.82rem;">${esc(data.error || "PIN lookup returned no results.")}</div>`;
        return;
      }
      if (targetCityInputId) {
        const cityEl = document.getElementById(targetCityInputId);
        if (cityEl && !cityEl.value.trim() && data.district) {
          cityEl.value = data.district;
        }
      }
      const listHtml = (data.post_offices || []).slice(0, 8).map(function (po) {
        return `<li><strong>${esc(po.name)}</strong> (${esc(po.branch_type || "PO")}) &mdash; ${esc(po.district || "")}, ${esc(po.state || "")}</li>`;
      }).join("");
      const more = data.post_office_count > 8 ? `<div class="text-dim" style="font-size:0.75rem;">+ ${data.post_office_count - 8} more Post Office(s) share PIN ${esc(data.pin_code)}</div>` : "";
      out.innerHTML = `
        <div style="padding:0.65rem 0.75rem; border-radius:8px; border:1px solid rgba(56,189,248,0.28); background:rgba(15,23,42,0.6); font-size:0.82rem;">
          <div><strong>PIN ${esc(data.pin_code)}:</strong> ${esc(data.district || "District")}, ${esc(data.state || "State")} (${Number(data.post_office_count)} Post Offices)</div>
          <ul style="margin:0.35rem 0 0.3rem 1.1rem; padding:0;">${listHtml}</ul>
          ${more}
          <div class="text-dim" style="font-size:0.74rem; margin-top:0.25rem;">${esc(data.disclaimer)}</div>
        </div>`;
    } catch (_) {
      out.innerHTML = '<div style="color:#ef4444; font-size:0.82rem;">PIN code service temporarily unavailable.</div>';
    }
  }

  registerLeafletHook();

  function mountStationsFinderBar() {
    const mapEl = document.getElementById("stationsMap");
    if (!mapEl || document.getElementById("evGeoSearchForm")) return;
    const panel = document.createElement("div");
    panel.id = "evGeoFinderPanel";
    panel.className = "card";
    panel.style.marginBottom = "1rem";
    panel.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.75rem;">
        <div>
          <strong style="font-size:1rem;"><i class="fa-solid fa-route" style="color:#10b981;"></i> Address / Area Navigation &amp; Indian PIN Assistant</strong>
          <div class="text-dim" style="font-size:0.78rem;">Explicit-submit Nominatim search &amp; OSRM driving directions (OSM ODbL · never keystroke autocomplete)</div>
        </div>
        <div style="display:flex; gap:0.45rem; flex-wrap:wrap;">
          <button type="button" id="evUseGpsBtn" class="btn btn-secondary btn-sm"><i class="fa-solid fa-location-crosshairs"></i> Use My GPS</button>
          <button type="button" id="evToggleReversePickBtn" class="btn btn-secondary btn-sm">Pick Pin on Map</button>
        </div>
      </div>
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:0.75rem;">
        <form id="evGeoSearchForm" style="display:flex; gap:0.5rem;">
          <input id="evGeoSearchInput" type="text" class="form-control" placeholder="Enter locality, city, or landmark (submit to search)" aria-label="Search area via Nominatim">
          <button type="submit" class="btn btn-primary btn-sm">Find Nearby</button>
        </form>
        <div style="display:flex; gap:0.5rem;">
          <input id="evDirectoryPinInput" type="text" maxlength="6" class="form-control" placeholder="6-digit Indian PIN (e.g. 110001)" aria-label="Lookup Indian PIN code">
          <button type="button" id="evDirectoryPinBtn" class="btn btn-secondary btn-sm">PIN Info</button>
        </div>
      </div>
      <div id="evGeoStatusPanel" style="margin-top:0.65rem; font-size:0.84rem;"></div>
      <div id="evDirectoryPinResult" style="margin-top:0.55rem;"></div>
      <div id="evNearbyResults"></div>
      <div id="evRouteSummaryPanel" style="margin-top:0.65rem; font-size:0.86rem;"></div>
    `;
    const parentCard = mapEl.closest(".card") || mapEl.parentNode;
    parentCard.parentNode.insertBefore(panel, parentCard);
  }

  function mountStationDetailWidgets() {
    const detailMapEl = document.getElementById("detailMap");
    if (!detailMapEl || document.getElementById("stationWeatherWidget")) return;
    let st = null;
    try {
      const jsonEl = document.getElementById("detailStationJson");
      const arr = jsonEl ? JSON.parse(jsonEl.textContent || "[]") : [];
      st = arr[0] || null;
    } catch (_) {}
    if (!st || st.latitude == null || st.longitude == null) return;

    const wrapper = document.createElement("div");
    wrapper.className = "grid-2 mb-4";
    wrapper.style.marginBottom = "1.25rem";
    wrapper.innerHTML = `
      <div class="card" id="stationWeatherWidget" data-lat="${Number(st.latitude)}" data-lng="${Number(st.longitude)}">
        <h2 style="font-size:1.1rem; margin-bottom:0.65rem;"><i class="fa-solid fa-cloud-sun" style="color:#38bdf8;"></i> Local Weather &amp; Short Forecast</h2>
        <div id="stationWeatherBody" class="text-dim" style="font-size:0.86rem;">Loading Open-Meteo telemetry...</div>
      </div>
      <div class="card">
        <h2 style="font-size:1.1rem; margin-bottom:0.65rem;"><i class="fa-solid fa-diamond-turn-right" style="color:#10b981;"></i> Driving Route &amp; Directions (OSRM)</h2>
        <form id="evDetailRouteForm" data-dest-lat="${Number(st.latitude)}" data-dest-lng="${Number(st.longitude)}" data-dest-name="${esc(st.station_name)}" style="display:flex; gap:0.5rem; flex-wrap:wrap;">
          <input id="evRouteOriginInput" type="text" class="form-control" style="flex:1; min-width:180px;" placeholder="Enter starting landmark or city (e.g. India Gate, New Delhi)">
          <button type="submit" class="btn btn-primary btn-sm">Get Route</button>
          <button type="button" id="evDetailGpsRouteBtn" class="btn btn-secondary btn-sm" data-dest-lat="${Number(st.latitude)}" data-dest-lng="${Number(st.longitude)}" data-dest-name="${esc(st.station_name)}">Use My GPS</button>
        </form>
        <div id="evGeoStatusPanel" style="margin-top:0.5rem; font-size:0.82rem;"></div>
        <div id="evRouteSummaryPanel" style="margin-top:0.6rem; font-size:0.86rem;"></div>
      </div>
    `;
    const parentGrid = detailMapEl.closest(".grid-cols-2") || detailMapEl.closest(".card");
    if (parentGrid && parentGrid.parentNode) {
      parentGrid.parentNode.insertBefore(wrapper, parentGrid.nextSibling);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    registerLeafletHook();
    mountStationsFinderBar();
    mountStationDetailWidgets();

    const dirPinBtn = document.getElementById("evDirectoryPinBtn");
    if (dirPinBtn) {
      dirPinBtn.addEventListener("click", function () {
        lookupIndianPin("evDirectoryPinInput", "evDirectoryPinResult", null);
      });
    }

    const searchForm = document.getElementById("evGeoSearchForm");
    if (searchForm) {
      searchForm.addEventListener("submit", function (e) {
        e.preventDefault();
        const qInput = document.getElementById("evGeoSearchInput");
        submitGeocodeSearch(qInput ? qInput.value : "", "stationsMap", true);
      });
    }

    const pickBtn = document.getElementById("evToggleReversePickBtn");
    if (pickBtn) {
      pickBtn.addEventListener("click", function () {
        reversePickEnabled = !reversePickEnabled;
        pickBtn.classList.toggle("btn-primary", reversePickEnabled);
        pickBtn.classList.toggle("btn-secondary", !reversePickEnabled);
        pickBtn.textContent = reversePickEnabled ? "Click Any Point on Map..." : "Pick Pin on Map";
      });
    }

    const gpsBtn = document.getElementById("evUseGpsBtn");
    if (gpsBtn) {
      gpsBtn.addEventListener("click", function () {
        useBrowserGps("stationsMap");
      });
    }

    const weatherWidget = document.getElementById("stationWeatherWidget");
    if (weatherWidget) {
      loadStationWeather(weatherWidget.dataset.lat, weatherWidget.dataset.lng, "stationWeatherBody");
    }

    const detailRouteForm = document.getElementById("evDetailRouteForm");
    if (detailRouteForm) {
      detailRouteForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        const originInput = document.getElementById("evRouteOriginInput");
        const matched = await submitGeocodeSearch(originInput ? originInput.value : "", "detailMap", false);
        if (matched) {
          await routeToStation(
            detailRouteForm.dataset.destLat,
            detailRouteForm.dataset.destLng,
            detailRouteForm.dataset.destName,
            "detailMap"
          );
        }
      });
    }

    const detailGpsBtn = document.getElementById("evDetailGpsRouteBtn");
    if (detailGpsBtn) {
      detailGpsBtn.addEventListener("click", function () {
        useBrowserGps(
          "detailMap",
          detailGpsBtn.dataset.destLat,
          detailGpsBtn.dataset.destLng,
          detailGpsBtn.dataset.destName
        );
      });
    }
  });

  window.EVGeoWidget = {
    routeToStation: routeToStation,
    submitGeocodeSearch: submitGeocodeSearch,
    useBrowserGps: useBrowserGps,
    loadStationWeather: loadStationWeather,
    lookupIndianPin: lookupIndianPin,
  };
})();
