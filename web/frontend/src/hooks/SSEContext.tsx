import { createContext, useContext } from "react";
import type { SSEEvent } from "./useSSE";

export interface SSEValue { last: SSEEvent | null; reconnects: number }
export const SSEContext = createContext<SSEValue>({ last: null, reconnects: 0 });
export const useSSEContext = () => useContext(SSEContext);
