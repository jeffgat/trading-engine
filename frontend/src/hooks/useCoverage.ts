import { useState, useCallback, useEffect, useRef } from "react";
import type {
  InstrumentCoverage,
  TestingPlanItem,
  ParamCoverageDetail,
} from "../lib/types";

const POLL_INTERVAL_MS = 30_000;

interface UseCoverageReturn {
  coverage: InstrumentCoverage[];
  planItems: TestingPlanItem[];
  loading: boolean;
  paramCoverage: Record<string, Record<string, ParamCoverageDetail>>;
  refreshCoverage: () => Promise<void>;
  loadParamCoverage: (instrument: string) => Promise<void>;
  createPlanItem: (
    instrument: string,
    title: string,
    notes?: string
  ) => Promise<TestingPlanItem | null>;
  updatePlanItem: (
    id: number,
    updates: { title?: string; notes?: string; status?: string }
  ) => Promise<void>;
  deletePlanItem: (id: number) => Promise<void>;
}

export function useCoverage(): UseCoverageReturn {
  const [coverage, setCoverage] = useState<InstrumentCoverage[]>([]);
  const [planItems, setPlanItems] = useState<TestingPlanItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [paramCoverage, setParamCoverage] = useState<
    Record<string, Record<string, ParamCoverageDetail>>
  >({});
  const initialLoad = useRef(true);

  const refreshCoverage = useCallback(async () => {
    if (initialLoad.current) {
      setLoading(true);
      initialLoad.current = false;
    }
    try {
      const [covRes, planRes] = await Promise.all([
        fetch("/api/coverage"),
        fetch("/api/testing-plan"),
      ]);
      if (covRes.ok) {
        const data = await covRes.json();
        setCoverage(data.result ?? data);
      }
      if (planRes.ok) {
        const data = await planRes.json();
        setPlanItems(data.result ?? data);
      }
    } catch {
      // API unavailable
    } finally {
      setLoading(false);
    }
  }, []);

  const loadParamCoverage = useCallback(async (instrument: string) => {
    try {
      const res = await fetch(`/api/coverage/${instrument}/params`);
      if (res.ok) {
        const data = await res.json();
        setParamCoverage((prev) => ({
          ...prev,
          [instrument]: data.result ?? data,
        }));
      }
    } catch {
      // ignore
    }
  }, []);

  const createPlanItem = useCallback(
    async (
      instrument: string,
      title: string,
      notes?: string
    ): Promise<TestingPlanItem | null> => {
      try {
        const res = await fetch("/api/testing-plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ instrument, title, notes }),
        });
        if (!res.ok) return null;
        const json = await res.json();
        const item: TestingPlanItem = json.result ?? json;
        setPlanItems((prev) => [...prev, item]);
        return item;
      } catch {
        return null;
      }
    },
    []
  );

  const updatePlanItem = useCallback(
    async (
      id: number,
      updates: { title?: string; notes?: string; status?: string }
    ) => {
      try {
        const res = await fetch(`/api/testing-plan/${id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        });
        if (res.ok) {
          const json = await res.json();
          const updated: TestingPlanItem = json.result ?? json;
          setPlanItems((prev) =>
            prev.map((item) => (item.id === id ? updated : item))
          );
        }
      } catch {
        // ignore
      }
    },
    []
  );

  const deletePlanItem = useCallback(async (id: number) => {
    try {
      await fetch(`/api/testing-plan/${id}`, { method: "DELETE" });
      setPlanItems((prev) => prev.filter((item) => item.id !== id));
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    refreshCoverage();
    const id = setInterval(refreshCoverage, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshCoverage]);

  return {
    coverage,
    planItems,
    loading,
    paramCoverage,
    refreshCoverage,
    loadParamCoverage,
    createPlanItem,
    updatePlanItem,
    deletePlanItem,
  };
}
