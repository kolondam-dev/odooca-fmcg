import { useEffect, useRef } from "preact/hooks";
import type * as Leaflet from "leaflet";
import type { MapFix, MapSite } from "../domain/checkin-map";
import "leaflet/dist/leaflet.css";
// Imported only after tile consent. GPS updates move markers without replacing
// the map, so the user's zoom/pan and privacy choice survive a fresh fix.
export function InteractiveMap({
    site,
    fix,
    zoom,
    ready,
    loading,
    recenter,
    failed,
    changed,
}: {
    site: MapSite;
    fix?: MapFix;
    zoom?: number;
    ready: () => void;
    loading: () => void;
    recenter: number;
    failed: () => void;
    changed: (zoom: number) => void;
}) {
    const root = useRef<HTMLDivElement>(null);
    const state = useRef<
        | {
              map: Leaflet.Map;
              marker?: Leaflet.CircleMarker;
              accuracy?: Leaflet.Circle;
          }
        | undefined
    >(undefined);
    const latest = useRef({ site, fix, zoom, ready, loading, failed, changed });
    latest.current = { site, fix, zoom, ready, loading, failed, changed };
    const center = (map: Leaflet.Map) => {
        const { site, fix } = latest.current;
        if (!site || !Number.isFinite(site.latitude) || !Number.isFinite(site.longitude)) return;
        const points: Leaflet.LatLngTuple[] = [[site.latitude, site.longitude]];
        if (fix && Number.isFinite(fix.latitude) && Number.isFinite(fix.longitude)) {
            points.push([fix.latitude, fix.longitude]);
        }
        try {
            map.fitBounds(points, {
                padding: [35, 35],
                maxZoom: 18,
                animate: false,
            });
        } catch {
            // fallback safe center
            map.setView([site.latitude, site.longitude], 16, { animate: false });
        }
    };
    useEffect(() => {
        let cancelled = false;
        let observer: ResizeObserver | undefined;
        void import("leaflet")
            .then((L) => {
                if (cancelled || !root.current) return;
                const map = L.map(root.current, {
                    zoomControl: false,
                    attributionControl: false,
                    scrollWheelZoom: false,
                    maxZoom: 19,
                    minZoom: 0,
                });
                state.current = { map };
                L.circle([site.latitude, site.longitude], {
                    radius: site.radius,
                    color: "#15803d",
                    weight: 2,
                }).addTo(map);
                L.circleMarker([site.latitude, site.longitude], {
                    radius: 7,
                    color: "#15803d",
                    fillOpacity: 1,
                })
                    .addTo(map)
                    .bindTooltip(site.name);
                const update = () => {
                    const fix = latest.current.fix;
                    if (!fix || !state.current) return;
                    if (!state.current.marker) {
                        state.current.marker = L.circleMarker(
                            [fix.latitude, fix.longitude],
                            { radius: 6, color: "#2563eb", fillOpacity: 1 },
                        ).addTo(map);
                        state.current.accuracy = L.circle(
                            [fix.latitude, fix.longitude],
                            {
                                radius: fix.accuracy,
                                color: "#2563eb",
                                weight: 1,
                                dashArray: "4 3",
                            },
                        ).addTo(map);
                    } else {
                        state.current.marker.setLatLng([
                            fix.latitude,
                            fix.longitude,
                        ]);
                        state.current.accuracy
                            ?.setLatLng([fix.latitude, fix.longitude])
                            .setRadius(fix.accuracy);
                    }
                };
                update();
                map.on("locationupdate", update);
                L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
                    maxZoom: 19,
                    referrerPolicy: "strict-origin-when-cross-origin",
                })
                    .on("loading", () => latest.current.loading())
                    .on("load", () => latest.current.ready())
                    .on("tileerror", () => latest.current.failed())
                    .addTo(map);
                center(map);
                if (latest.current.zoom !== undefined)
                    map.setZoom(latest.current.zoom, { animate: false });
                setTimeout(() => {
                    if (!cancelled && root.current) {
                        map.invalidateSize({ pan: false });
                        center(map);
                    }
                }, 150);
                map.on("zoomend", () => {
                    root.current?.setAttribute(
                        "data-zoom",
                        String(map.getZoom()),
                    );
                    latest.current.changed(map.getZoom());
                });
                root.current.setAttribute("data-zoom", String(map.getZoom()));
                observer = new ResizeObserver(() =>
                    map.invalidateSize({ pan: false }),
                );
                observer.observe(root.current);
            })
            .catch(() => {
                if (!cancelled) latest.current.failed();
            });
        return () => {
            cancelled = true;
            observer?.disconnect();
            state.current?.map.remove();
            state.current = undefined;
        };
    }, []);
    useEffect(() => {
        state.current?.map.fire("locationupdate");
    }, [fix]);
    useEffect(() => {
        const map = state.current?.map;
        if (!map) return;
        if (zoom === undefined) center(map);
        else if (map.getZoom() !== zoom) map.setZoom(zoom, { animate: false });
    }, [zoom, recenter]);
    return (
        <div
            ref={root}
            class="interactive-map"
            aria-label="Peta interaktif; geser atau cubit untuk mengatur peta"
        />
    );
}
