"use client";

import { createContext, useContext } from "react";

export type ProjectT = {
  id: string;
  name: string;
  code: string | null;
  location: string | null;
  contract_form: string | null;
  holiday_region: string;
  shutdowns: { id: string; name: string; start: string; end: string }[];
  parties: { id: string; name: string; organisation: string | null; role: string; email: string | null }[];
  stats: Record<string, number>;
};

export const Ctx = createContext<{ project: ProjectT | null; reload: () => void; system: any }>({ project: null, reload: () => {}, system: null });
export const useProject = () => useContext(Ctx);

