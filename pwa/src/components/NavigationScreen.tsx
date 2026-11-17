import { useEffect, useState } from "preact/hooks";
import { Button, Callout, Screen, ScreenHeader } from "../ui";
import { Icon } from "./Icon";
import { navigationUrl } from "../domain/delivery-progress";
import {
    schematicMap,
    straightLineLabel,
    type NavFix,
    type NavTarget,
} from "../domain/navigation-target";
import { captureVisitLocation } from "../domain/visits";

type Locate = (source?: (value: "device" | "demo") => void) => Promise<NavFix>;

/**
 * Layar Navigasi DS: skema posisi, nama dan alamat tujuan, jarak garis lurus,
 * "Buka di Google Maps" dan "Saya sudah tiba · Check-in".
 * Lokasi perangkat dibaca satu kali setelah pengguna membuka layar ini dan
 * hanya dipakai untuk tampilan; tidak menjadi bukti check-in dan tidak disimpan.
 */
export function NavigationScreen({
    target,
    fallbackDistance,
    onBack,
    onArrive,
    locate = captureVisitLocation,
}: {
    target: NavTarget;
    /** Jarak dari snapshot (`outlet.distance`) bila posisi perangkat belum ada. */
    fallbackDistance?: string;
    onBack: () => void;
    onArrive: () => void;
    locate?: Locate;
}) {
    const [fix, setFix] = useState<NavFix>();
    const [state, setState] = useState<"loading" | "ready" | "unavailable">(
        "loading",
    );
    const [simulated, setSimulated] = useState(false);
    useEffect(() => {
        let active = true;
        setFix(undefined);
        setSimulated(false);
        setState("loading");
        locate((source) => active && setSimulated(source === "demo")).then(
            (p) => {
                if (!active) return;
                setFix({ latitude: p.latitude, longitude: p.longitude });
                setState("ready");
            },
            () => active && setState("unavailable"),
        );
        return () => {
            active = false;
        };
    }, [target.latitude, target.longitude]);
    const map = schematicMap(target, fix);
    const distance = straightLineLabel(target, fix);
    return (
        <Screen
            label="Navigasi"
            class="ui-screen--over"
            flush
            header={<ScreenHeader title="Navigasi" onBack={onBack} />}
            footer={
                <Button icon="pin" onClick={onArrive}>
                    Saya sudah tiba · Check-in
                </Button>
            }
        >
            <div class="ui-navmap" role="img" aria-label="Peta area">
                <svg
                    viewBox={`0 0 ${map.width} ${map.height}`}
                    preserveAspectRatio="xMidYMid meet"
                    aria-hidden="true"
                >
                    {map.line && map.user ? (
                        <line
                            class="ui-navmap__route"
                            x1={map.user.x}
                            y1={map.user.y}
                            x2={map.target.x}
                            y2={map.target.y}
                        />
                    ) : null}
                    {map.user ? (
                        <>
                            <circle
                                class="ui-navmap__halo"
                                cx={map.user.x}
                                cy={map.user.y}
                                r="14"
                            />
                            <circle
                                class="ui-navmap__me"
                                cx={map.user.x}
                                cy={map.user.y}
                                r="7"
                            />
                        </>
                    ) : null}
                    <g
                        class="ui-navmap__pin"
                        transform={`translate(${map.target.x} ${map.target.y}) scale(1.4) translate(-14 -28)`}
                    >
                        <path d="M14 28s7-6.2 7-11.5A7 7 0 0 0 7 16.5C7 21.8 14 28 14 28z" />
                        <circle cx="14" cy="16.5" r="2.5" />
                    </g>
                </svg>
                <span class="ui-navmap__cap">
                    Skema garis lurus, bukan rute jalan
                </span>
            </div>
            <div class="ui-navinfo">
                <h2 class="ui-navinfo__name">{target.name}</h2>
                <span class="ui-row__sub">{target.address}</span>
                {distance ? (
                    <div class="ui-meta">
                        <span class="ui-meta__i">
                            <Icon name="pin" size={18} />
                            {distance}
                            {simulated ? " · posisi simulasi" : ""}
                        </span>
                    </div>
                ) : state === "loading" ? (
                    <div class="ui-meta" role="status">
                        <span class="ui-meta__i">
                            <Icon name="pin" size={18} />
                            Mencari lokasi perangkat…
                        </span>
                    </div>
                ) : (
                    <>
                        {fallbackDistance ? (
                            <div class="ui-meta">
                                <span class="ui-meta__i">
                                    <Icon name="pin" size={18} />
                                    {fallbackDistance}
                                </span>
                            </div>
                        ) : null}
                        <Callout tone="warn" icon="pin">
                            Lokasi perangkat belum tersedia, jadi jarak dan
                            posisi Anda belum ditampilkan. Anda tetap bisa
                            membuka Google Maps.
                        </Callout>
                    </>
                )}
                <a
                    class="ui-btn ui-btn--sec ui-btn--md"
                    href={navigationUrl(target.latitude, target.longitude)}
                    target="_blank"
                    rel="noopener noreferrer"
                >
                    <Icon name="send" size={22} />
                    Buka di Google Maps
                </a>
            </div>
        </Screen>
    );
}
