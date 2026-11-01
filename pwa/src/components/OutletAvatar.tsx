import { useEffect, useState } from "preact/hooks";
import { Icon } from "./Icon";
export function OutletAvatar({
    url,
    name = "",
}: {
    url?: string | null;
    name?: string;
}) {
    const [failed, setFailed] = useState(false);
    useEffect(() => setFailed(false), [url]);
    return url && !failed ? (
        <img
            class="outlet-avatar"
            src={url}
            alt={name ? `Logo ${name}` : ""}
            loading="lazy"
            onError={() => setFailed(true)}
        />
    ) : (
        <span class="outlet-avatar">
            <Icon name="store" size={28} />
        </span>
    );
}
