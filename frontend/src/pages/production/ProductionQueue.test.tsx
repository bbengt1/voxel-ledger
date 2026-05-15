import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ProductionQueuePage } from "@/pages/production/ProductionQueue";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

const ORD = "11111111-1111-1111-1111-111111111111";
const J1 = "22222222-2222-2222-2222-222222222222";
const J2 = "33333333-3333-3333-3333-333333333333";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/production/queue"]}>
      <AppProviders>
        <Routes>
          <Route path="/production/queue" element={<ProductionQueuePage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

function makeOrder(jobs: { job_id: string; display_order: number }[]) {
  return {
    id: ORD,
    order_number: "PO-2026-0001",
    name: "Etsy spring batch",
    state: "planning" as const,
    priority: 0,
    due_at: null,
    notes: null,
    created_by_user_id: "u",
    jobs,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function makeJob(id: string, jobNumber: string, state = "queued") {
  return {
    id,
    job_number: jobNumber,
    state,
    quantity_ordered: 10,
    pieces_produced: 4,
    priority: 0,
    product_id: "pid",
    actor_user_id: "u",
    plates: [],
    notes: null,
    due_at: null,
    customer_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("<ProductionQueuePage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders orders and their jobs in display order", async () => {
    mock.onGet("/api/v1/production-orders").reply(200, {
      items: [
        makeOrder([
          { job_id: J1, display_order: 0 },
          { job_id: J2, display_order: 1 },
        ]),
      ],
      next_cursor: null,
    });
    mock.onGet("/api/v1/jobs").reply(200, { items: [], next_cursor: null });
    mock.onGet(`/api/v1/jobs/${J1}`).reply(200, makeJob(J1, "JOB-1"));
    mock.onGet(`/api/v1/jobs/${J2}`).reply(200, makeJob(J2, "JOB-2"));

    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId(`order-${ORD}`)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText("JOB-1")).toBeInTheDocument();
      expect(screen.getByText("JOB-2")).toBeInTheDocument();
    });
  });

  it("creates a new production order", async () => {
    const user = userEvent.setup();
    let createdName = "";
    mock.onGet("/api/v1/production-orders").reply(200, {
      items: [],
      next_cursor: null,
    });
    mock.onGet("/api/v1/jobs").reply(200, { items: [], next_cursor: null });
    mock.onPost("/api/v1/production-orders").reply((config) => {
      const body = JSON.parse(config.data as string);
      createdName = body.name;
      return [
        201,
        makeOrder([]),
      ];
    });

    renderPage();
    await user.click(await screen.findByTestId("new-order-btn"));
    await user.type(
      screen.getByTestId("new-order-name-input"),
      "Holiday rush",
    );
    await user.click(screen.getByTestId("new-order-submit"));

    await waitFor(() => expect(createdName).toBe("Holiday rush"));
  });

  it("reorders jobs via drag-and-drop", async () => {
    let reorderCalled: { job_id: string; new_position: number } | null = null;
    mock.onGet("/api/v1/production-orders").reply(200, {
      items: [
        makeOrder([
          { job_id: J1, display_order: 0 },
          { job_id: J2, display_order: 1 },
        ]),
      ],
      next_cursor: null,
    });
    mock.onGet("/api/v1/jobs").reply(200, { items: [], next_cursor: null });
    mock.onGet(`/api/v1/jobs/${J1}`).reply(200, makeJob(J1, "JOB-1"));
    mock.onGet(`/api/v1/jobs/${J2}`).reply(200, makeJob(J2, "JOB-2"));
    mock.onPatch(`/api/v1/production-orders/${ORD}/jobs`).reply((config) => {
      reorderCalled = JSON.parse(config.data as string);
      return [200, {}];
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId(`order-job-${J1}`)).toBeInTheDocument();
      expect(screen.getByTestId(`order-job-${J2}`)).toBeInTheDocument();
    });

    // Simulate drag of J2 onto J1's slot (position 0). jsdom lacks a real
    // DragEvent, so we synthesize an Event and attach a fake dataTransfer.
    const dataTransfer = {
      data: {} as Record<string, string>,
      setData(key: string, val: string) {
        this.data[key] = val;
      },
      getData(key: string) {
        return this.data[key] ?? "";
      },
    };
    function fireDrag(target: Element, type: string) {
      const ev = new Event(type, { bubbles: true, cancelable: true });
      Object.defineProperty(ev, "dataTransfer", { value: dataTransfer });
      target.dispatchEvent(ev);
    }
    fireDrag(screen.getByTestId(`order-job-${J2}`), "dragstart");
    fireDrag(screen.getByTestId(`order-job-${J1}`), "dragover");
    fireDrag(screen.getByTestId(`order-job-${J1}`), "drop");

    await waitFor(() => {
      expect(reorderCalled).not.toBeNull();
    });
    expect(reorderCalled).toEqual({ job_id: J2, new_position: 0 });
  });
});
