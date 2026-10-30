import { useLayoutEffect, useRef, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import type { MapFix } from "../domain/checkin-map";
import { CheckinMap } from "./CheckinMap";

export function OfficialMaps({ snapshot }: { snapshot: Snapshot }) {
    const [selected, setSelected] = useState(
        snapshot.office ? "office" : `outlet:${snapshot.outlets[0]?.id}`,
    );
    const [fix, setFix] = useState<MapFix>();
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    const generation = useRef(0);
    useLayoutEffect(() => {
        generation.current++;
        setFix(undefined);
        setMessage("");
        setBusy(false);
        return () => {
            generation.current++;
        };
    }, [selected, snapshot.version]);
    const office = selected === "office" ? snapshot.office : undefined;
    const outlet = snapshot.outlets.find((o) => `outlet:${o.id}` === selected);
    const site = office
        ? {
              ...office,
              name: `Kantor: ${office.name}`,
              simulated: office.coordinate_status === "test",
          }
        : outlet
          ? { ...outlet, name: `Outlet: ${outlet.name}` }
          : undefined;
    function locate() {
        const ticket = ++generation.current;
        setFix(undefined);
        setMessage("");
        setBusy(true);
        if (!navigator.geolocation) {
            setBusy(false);
            setMessage(
                "Lokasi perangkat tidak tersedia. Tidak ada posisi pengganti.",
            );
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (p) => {
                if (generation.current !== ticket) return;
                setFix({
                    latitude: p.coords.latitude,
                    longitude: p.coords.longitude,
                    accuracy: p.coords.accuracy,
                });
                setBusy(false);
            },
            () => {
                if (generation.current !== ticket) return;
                setBusy(false);
                setMessage(
                    "Izin lokasi ditolak atau lokasi gagal diperoleh. Tidak ada posisi pengganti.",
                );
            },
            { enableHighAccuracy: true, maximumAge: 0, timeout: 12000 },
        );
    }
    return (
        <section class="read-card" aria-label="Preview lokasi check-in staging">
            <h2>Preview lokasi kantor / outlet</h2>
            <p>
                Koordinat tujuan dari snapshot Odoo. Tampilan ini belum mencatat
                check-in kantor atau kunjungan outlet.
            </p>
            {!snapshot.office && (
                <p>Master kantor belum ditetapkan pada assignment hari ini.</p>
            )}
            <label>
                Tujuan preview
                <select
                    aria-label="Tujuan preview staging"
                    value={selected}
                    onChange={(e) => setSelected(e.currentTarget.value)}
                >
                    {snapshot.office && (
                        <option value="office">
                            Kantor: {snapshot.office.name}
                        </option>
                    )}
                    {snapshot.outlets.map((o) => (
                        <option key={o.id} value={`outlet:${o.id}`}>
                            Outlet: {o.name}
                        </option>
                    ))}
                </select>
            </label>
            {office && (
                <p>
                    Status koordinat kantor:{" "}
                    <strong>
                        {office.coordinate_status === "verified"
                            ? "Terverifikasi oleh admin"
                            : office.coordinate_status === "test"
                              ? "TEST · titik uji, bukan kantor nyata"
                              : "Belum diverifikasi"}
                    </strong>
                </p>
            )}
            <button class="secondary" disabled={busy || !site} onClick={locate}>
                {busy
                    ? "Mengambil posisi perangkat…"
                    : "Ambil posisi untuk preview"}
            </button>
            {message && <p role="status">{message}</p>}
            {site && (
                <CheckinMap
                    key={`${snapshot.version}:${selected}`}
                    site={site}
                    fix={fix}
                />
            )}
            <p class="footnote">
                Preview tidak mengunggah lokasi/foto. Geofence evidence server
                tetap strict; tidak ada pengecualian berdasarkan peta ini.
            </p>
        </section>
    );
}
