/* ============================================================
   EV ChargeNet — Interactive Map Controller
   Primary: Google Maps JavaScript API (+ Places) when key is set
   Fallback: Leaflet.js + OpenStreetMap interactive slippy map
   Always driven by real MySQL Stations records via JSON/API
   ============================================================ */

(function () {
  "use strict";

  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    const toRad = (deg) => (deg * Math.PI) / 180;
    const R = 6371;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
      Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function buildInfoHtml(st, distKm) {
    const mapsUrl = st.maps_url || `https://www.google.com/maps/search/?api=1&query=${st.latitude},${st.longitude}`;
    const dirUrl = `https://www.google.com/maps/dir/?api=1&destination=${st.latitude},${st.longitude}`;
    const verif = escapeHtml(st.verification_status || "DEMO");
    const facs = Array.isArray(st.facilities) && st.facilities.length
      ? st.facilities.slice(0, 4).map(escapeHtml).join(" · ")
      : "Public Access";
    const distLine = distKm != null ? `<div style="margin-top:4px;font-size:12px;color:#059669;font-weight:600;">Distance: ${distKm.toFixed(1)} km away</div>` : "";

    return `
      <div style="font-family:Inter,system-ui,sans-serif;max-width:280px;color:#0f172a;line-height:1.4;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:4px;">
          <span style="font-size:11px;font-weight:700;padding:2px 6px;border-radius:4px;background:${verif === "VERIFIED" ? "#d1fae5" : "#e2e8f0"};color:${verif === "VERIFIED" ? "#065f46" : "#334155"};">${verif} LOCATION</span>
          <span style="font-size:11px;color:#475569;">${escapeHtml(st.city)}</span>
        </div>
        <div style="font-weight:800;font-size:14px;margin-bottom:2px;">${escapeHtml(st.station_name)}</div>
        <div style="font-size:12px;color:#475569;margin-bottom:6px;">${escapeHtml(st.address)}${st.postal_code ? " — " + escapeHtml(st.postal_code) : ""}</div>
        <div style="font-size:12px;"><strong>Operator:</strong> ${escapeHtml(st.operator_name || "Tata Power EZ Charge")}</div>
        <div style="font-size:12px;"><strong>Connectors:</strong> ${escapeHtml(st.connector_types || "CCS2")} (${escapeHtml(st.charger_capacity_kw || "DC/AC")})</div>
        <div style="font-size:12px;"><strong>Points:</strong> ${Number(st.available_points || 0)} / ${Number(st.total_points || 0)} &mdash; Availability not connected (demonstration data)</div>
        <div style="font-size:11px;color:#64748b;margin-top:4px;"><strong>Facilities:</strong> ${facs}</div>
        ${distLine}
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;">
          <a href="/stations/${Number(st.station_id)}" style="background:#0f172a;color:#fff;padding:5px 9px;border-radius:6px;font-size:11px;font-weight:600;text-decoration:none;">Inspect &amp; Book</a>
          <a href="${escapeHtml(dirUrl)}" target="_blank" rel="noopener noreferrer" style="background:#10b981;color:#fff;padding:5px 9px;border-radius:6px;font-size:11px;font-weight:600;text-decoration:none;">Directions</a>
          <a href="${escapeHtml(mapsUrl)}" target="_blank" rel="noopener noreferrer" style="background:#e2e8f0;color:#0f172a;padding:5px 9px;border-radius:6px;font-size:11px;font-weight:600;text-decoration:none;">Google Maps</a>
        </div>
      </div>
    `;
  }

  function loadLeafletFallback(container, stations, statusBadge, userCoords) {
    const cssId = "leaflet-css-cdn";
    if (!document.getElementById(cssId)) {
      const link = document.createElement("link");
      link.id = cssId;
      link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(link);
    }

    const startLeaflet = () => {
      if (!window.L) {
        container.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--text-muted);">Map engine unavailable offline. Station links below remain active for Google Maps navigation.</div>`;
        return;
      }
      container.innerHTML = "";
      const centerLat = stations.length ? stations[0].latitude : 28.6139;
      const centerLng = stations.length ? stations[0].longitude : 77.2090;
      const map = window.L.map(container).setView([centerLat, centerLng], stations.length === 1 ? 14 : 10);

      window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(map);

      const bounds = [];
      stations.forEach((st) => {
        if (st.latitude == null || st.longitude == null) return;
        const distKm = userCoords ? haversineKm(userCoords.lat, userCoords.lng, st.latitude, st.longitude) : null;
        const marker = window.L.marker([st.latitude, st.longitude]).addTo(map);
        marker.bindPopup(buildInfoHtml(st, distKm));
        bounds.push([st.latitude, st.longitude]);
      });

      if (userCoords) {
        window.L.circleMarker([userCoords.lat, userCoords.lng], {
          radius: 8,
          color: "#06b6d4",
          fillColor: "#06b6d4",
          fillOpacity: 0.7,
        }).addTo(map).bindPopup("<strong>Your Current Location</strong>");
        bounds.push([userCoords.lat, userCoords.lng]);
      }

      if (bounds.length > 1) {
        map.fitBounds(bounds, { padding: [32, 32] });
      }
      if (statusBadge) {
        statusBadge.textContent = "Interactive Map: OpenStreetMap Fallback (Configure GOOGLE_MAPS_API_KEY for Google Maps)";
      }
    };

    if (window.L) {
      startLeaflet();
    } else {
      const script = document.createElement("script");
      script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      script.onload = startLeaflet;
      script.onerror = () => {
        container.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--text-muted);">Unable to load map tiles. Use the "Open in Google Maps" links on any station card.</div>`;
      };
      document.body.appendChild(script);
    }
  }

  function initGoogleMapsEngine(container, stations, apiKey, statusBadge, userCoords) {
    let fallbackTriggered = false;
    const triggerFallback = () => {
      if (fallbackTriggered) return;
      fallbackTriggered = true;
      loadLeafletFallback(container, stations, statusBadge, userCoords);
    };

    window.gm_authFailure = triggerFallback;

    const renderGMap = () => {
      if (!window.google || !window.google.maps) {
        triggerFallback();
        return;
      }
      const center = stations.length
        ? { lat: Number(stations[0].latitude), lng: Number(stations[0].longitude) }
        : { lat: 28.6139, lng: 77.2090 };
      const map = new window.google.maps.Map(container, {
        center,
        zoom: stations.length === 1 ? 14 : 10,
        mapTypeControl: true,
        streetViewControl: false,
      });

      const infoWin = new window.google.maps.InfoWindow();
      const bounds = new window.google.maps.LatLngBounds();

      stations.forEach((st) => {
        if (st.latitude == null || st.longitude == null) return;
        const pos = { lat: Number(st.latitude), lng: Number(st.longitude) };
        const marker = new window.google.maps.Marker({
          position: pos,
          map,
          title: st.station_name,
        });
        bounds.extend(pos);
        marker.addListener("click", () => {
          const distKm = userCoords ? haversineKm(userCoords.lat, userCoords.lng, st.latitude, st.longitude) : null;
          infoWin.setContent(buildInfoHtml(st, distKm));
          infoWin.open(map, marker);
        });
      });

      if (stations.length > 1) {
        map.fitBounds(bounds);
      }
      if (statusBadge) {
        statusBadge.textContent = "Interactive Map: Google Maps Platform Active";
      }
    };

    if (window.google && window.google.maps) {
      renderGMap();
    } else {
      window.__evInitGoogleMap = renderGMap;
      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=places&callback=__evInitGoogleMap`;
      script.async = true;
      script.defer = true;
      script.onerror = triggerFallback;
      document.head.appendChild(script);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const mapContainers = document.querySelectorAll("[data-ev-map]");
    mapContainers.forEach((container) => {
      const apiKey = (container.dataset.mapsKey || "").trim();
      const apiUrl = container.dataset.apiUrl || "";
      const inlineJsonId = container.dataset.stationsEl || "";
      const statusBadge = document.getElementById(container.dataset.statusTarget || "");
      const nearBtn = document.getElementById(container.dataset.nearBtn || "");

      const drawWithStations = (stations, userCoords = null) => {
        if (apiKey) {
          initGoogleMapsEngine(container, stations, apiKey, statusBadge, userCoords);
        } else {
          loadLeafletFallback(container, stations, statusBadge, userCoords);
        }
      };

      const loadStations = async (userCoords = null) => {
        if (inlineJsonId) {
          const scriptEl = document.getElementById(inlineJsonId);
          if (scriptEl) {
            try {
              const parsed = JSON.parse(scriptEl.textContent || "[]");
              drawWithStations(parsed, userCoords);
              return;
            } catch (_) {}
          }
        }
        if (apiUrl) {
          try {
            const resp = await fetch(apiUrl);
            const data = await resp.json();
            drawWithStations(data.stations || [], userCoords);
          } catch (_) {
            drawWithStations([], userCoords);
          }
        }
      };

      loadStations(null);

      if (nearBtn && navigator.geolocation) {
        nearBtn.addEventListener("click", () => {
          nearBtn.disabled = true;
          nearBtn.textContent = "Locating...";
          navigator.geolocation.getCurrentPosition(
            (pos) => {
              const coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
              nearBtn.disabled = false;
              nearBtn.textContent = "📍 Near Me Active";
              loadStations(coords);
            },
            () => {
              nearBtn.disabled = false;
              nearBtn.textContent = "📍 Use My Location";
              if (statusBadge) {
                statusBadge.textContent = "Location permission denied — showing full Delhi NCR grid.";
              }
            }
          );
        });
      }
    });
  });
})();

