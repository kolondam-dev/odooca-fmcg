import { InteractiveMap } from "./InteractiveMap";
import { useEffect, useState } from "preact/hooks";
import { checkinMap, type MapFix, type MapSite } from "../domain/checkin-map";
import { distanceMeters } from "../domain/format";
import { Button, Callout, Chip } from "../ui";
import { cx } from "../ui/cx";

// Display-only: this component never authorizes a check-in or changes evidence.
export function CheckinMap({
    site,
    fix,
    compact = false,
}: {
    site: MapSite;
    fix?: MapFix;
    compact?: boolean;
}) {
    const scope = JSON.stringify(site);
    const [enabled, setEnabled] = useState(false);
    const [zoom, setZoom] = useState<number>();
    const [recenter, setRecenter] = useState(0);
    const [failed, setFailed] = useState(false);
    const [ready, setReady] = useState(false);
    useEffect(() => {
        setZoom(undefined);
        setEnabled(false);
        setFailed(false);
        setReady(false);
    }, [scope]);
    let map: ReturnType<typeof checkinMap> | undefined;
    try {
        map = checkinMap(site, fix, zoom);
    } catch {
        /* Keep hook order stable even for corrupt coordinates. */
    }
    const tileKey = map?.tiles.map((t) => t.key).join(",") ?? "";
    useEffect(() => {
        if (!enabled || ready) return;
        const id = setTimeout(() => setFailed(true), 10000);
        return () => clearTimeout(id);
    }, [enabled, tileKey, ready]);
    if (!map)
        return (
            <Callout tone="warn">
                Preview peta tidak tersedia: koordinat tujuan/perangkat tidak
                valid.
            </Callout>
        );
    const distance = fix
        ? distanceMeters(
              site.latitude,
              site.longitude,
              fix.latitude,
              fix.longitude,
          )
        : undefined;
    const status = !fix
        ? "Posisi perangkat belum tersedia"
        : distance! + fix.accuracy <= site.radius
          ? "Di dalam radius"
          : distance! - fix.accuracy > site.radius
            ? "Di luar radius"
            : "Akurasi belum pasti";
    const outside = status === "Di luar radius";
    const tone = !fix
        ? "neu"
        : status === "Di dalam radius"
          ? "ok"
          : outside
            ? "bad"
            : "warn";
    const mark = outside ? "var(--c-bad)" : "var(--c-ok)";
    return (
        <section
            class={cx("ui-map", compact && "ui-map--compact")}
            aria-label={`Preview peta ${site.name}`}
        >
            <strong class="ui-map__title">Preview peta · {site.name}</strong>
            {(site.simulated || fix?.simulated) && (
                <p class="ui-map__sim">
                    {site.simulated
                        ? "Titik tujuan simulasi"
                        : "Titik tujuan paket"}
                    {fix?.simulated ? " · posisi simulasi" : ""} · bukan
                    validasi kehadiran resmi.
                </p>
            )}
            <p class="ui-map__status">
                <Chip tone={tone}>{status}</Chip>
                <span>
                    Radius {site.radius} m
                    {distance !== undefined && (
                        <>
                            {" "}
                            · Jarak {Math.round(distance)} m · Akurasi ±
                            {Math.round(fix!.accuracy)} m
                        </>
                    )}
                </span>
            </p>
            <div class="ui-map__canvas">
                {enabled && (
                    <InteractiveMap
                        key={scope}
                        site={site}
                        fix={fix}
                        zoom={zoom}
                        recenter={recenter}
                        loading={() => setReady(false)}
                        ready={() => setReady(true)}
                        failed={() => setFailed(true)}
                        changed={setZoom}
                    />
                )}
                <svg
                    hidden={enabled && !failed}
                    viewBox="0 0 512 320"
                    role="img"
                    aria-label="Titik tujuan hijau, posisi perangkat biru, lingkaran radius dan akurasi"
                >
                    <circle
                        cx={map.site.x}
                        cy={map.site.y}
                        r={map.site.radius}
                        fill={mark}
                        fill-opacity="0.14"
                        stroke={mark}
                        stroke-width="2"
                    />
                    {fix && (
                        <>
                            <line
                                x1={map.site.x}
                                y1={map.site.y}
                                x2={map.fix.x}
                                y2={map.fix.y}
                                stroke="var(--c-neu)"
                                stroke-dasharray="5 4"
                            />
                            <circle
                                cx={map.fix.x}
                                cy={map.fix.y}
                                r={map.fix.radius}
                                fill="var(--c-pri)"
                                fill-opacity="0.14"
                                stroke="var(--c-pri)"
                                stroke-dasharray="4 3"
                            />
                        </>
                    )}
                    <circle
                        cx={map.site.x}
                        cy={map.site.y}
                        r="7"
                        fill={mark}
                        stroke="var(--c-surface)"
                        stroke-width="2"
                    />
                    {fix && (
                        <circle
                            cx={map.fix.x}
                            cy={map.fix.y}
                            r="5"
                            fill="var(--c-pri)"
                            stroke="var(--c-surface)"
                            stroke-width="2"
                        />
                    )}
                </svg>
            </div>
            <small class="ui-map__coords">
                Hijau: tujuan · Biru: perangkat. {site.latitude.toFixed(6)},{" "}
                {site.longitude.toFixed(6)}
                {fix && (
                    <>
                        {" "}
                        · Posisi {fix.latitude.toFixed(6)},{" "}
                        {fix.longitude.toFixed(6)}
                    </>
                )}
            </small>
            {!enabled ? (
                <>
                    <p class="ui-map__note">
                        {compact
                            ? "Memuat OpenStreetMap membagikan IP dan area peta."
                            : "Muat peta jalan menghubungi OpenStreetMap dan membagikan area peta serta alamat IP. Foto dan identitas tidak dikirim. Diagram titik tetap tersedia tanpa jaringan."}
                    </p>
                    <Button
                        variant="sec"
                        size="md"
                        onClick={() => {
                            setFailed(false);
                            setReady(false);
                            setEnabled(true);
                        }}
                    >
                        Muat peta jalan
                    </Button>
                </>
            ) : (
                <>
                    <div class="ui-map__controls">
                        <Button
                            variant="sec"
                            size="sm"
                            auto
                            aria-label="Perbesar peta"
                            disabled={map.zoom >= 19}
                            onClick={() => {
                                setFailed(false);
                                setZoom(map.zoom + 1);
                            }}
                        >
                            +
                        </Button>
                        <Button
                            variant="sec"
                            size="sm"
                            auto
                            aria-label="Perkecil peta"
                            disabled={map.zoom <= 0}
                            onClick={() => {
                                setFailed(false);
                                setZoom(map.zoom - 1);
                            }}
                        >
                            −
                        </Button>
                        <Button
                            variant="sec"
                            size="sm"
                            auto
                            onClick={() => {
                                setFailed(false);
                                setRecenter((value) => value + 1);
                                setZoom(undefined);
                            }}
                        >
                            Tampilkan kedua titik
                        </Button>
                        <Button
                            variant="sec"
                            size="sm"
                            auto
                            onClick={() => setEnabled(false)}
                        >
                            Tutup peta jalan
                        </Button>
                    </div>
                    {failed ? (
                        <Callout tone="warn">
                            Peta jalan gagal atau belum lengkap. Diagram titik
                            tetap tersedia; ini bukan bukti keberhasilan
                            check-in.
                        </Callout>
                    ) : (
                        !ready && (
                            <Callout tone="neu">Memuat peta jalan…</Callout>
                        )
                    )}
                </>
            )}
            <small class="ui-map__credit">
                ©{" "}
                <a
                    href="https://www.openstreetmap.org/copyright"
                    target="_blank"
                    rel="noreferrer"
                >
                    OpenStreetMap contributors
                </a>{" "}
                ·{" "}
                <a
                    href="https://www.openstreetmap.org/fixthemap"
                    target="_blank"
                    rel="noreferrer"
                >
                    Laporkan masalah peta
                </a>
            </small>
        </section>
    );
}
