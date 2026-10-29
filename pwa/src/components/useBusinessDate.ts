import { useEffect, useState } from "preact/hooks";
import { fieldBusinessDate } from "../domain/morning";
export function useBusinessDate() {
    const [day, setDay] = useState(fieldBusinessDate);
    useEffect(() => {
        const refresh = () => setDay(fieldBusinessDate());
        const timer = window.setInterval(refresh, 1000);
        window.addEventListener("focus", refresh);
        return () => {
            window.clearInterval(timer);
            window.removeEventListener("focus", refresh);
        };
    }, []);
    return day;
}
