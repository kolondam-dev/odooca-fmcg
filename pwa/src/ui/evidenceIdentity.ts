import { createContext } from "preact";
export const EvidenceIdentityContext = createContext<
    { company: string; employee: string } | undefined
>(undefined);
