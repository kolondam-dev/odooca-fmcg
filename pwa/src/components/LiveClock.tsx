import { useEffect, useState } from "preact/hooks";
const formatter = new Intl.DateTimeFormat("id-ID", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Makassar",
});
// Keep the second hand out of the catalog, forms and workspace render tree.
export function LiveClock() {
    const [now, setNow] = useState(Date.now());
    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, []);
    return (
        <time dateTime={new Date(now).toISOString()}>
            {formatter.format(now)} · WITA
        </time>
    );
}
