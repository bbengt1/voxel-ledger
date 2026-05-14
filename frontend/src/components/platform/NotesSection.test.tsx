import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { NotesSection } from "@/components/platform/NotesSection";
import { useAuthStore } from "@/store/useAuthStore";

const ENTITY_ID = "11111111-1111-1111-1111-111111111111";
const USER_ID = "u-1";

function setUser(role: "owner" | "production") {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: USER_ID, email: "u@example.com", role },
  });
}

function aNote(
  overrides: Partial<{
    id: string;
    body: string;
    is_pinned: boolean;
    author_user_id: string;
  }> = {},
) {
  return {
    id: "n-1",
    entity_kind: "material",
    entity_id: ENTITY_ID,
    body: "hello world",
    author_user_id: USER_ID,
    is_pinned: false,
    created_at: "2026-05-14T12:00:00Z",
    updated_at: "2026-05-14T12:00:00Z",
    ...overrides,
  };
}

function renderSection() {
  return render(
    <AppProviders>
      <NotesSection entityKind="material" entityId={ENTITY_ID} />
    </AppProviders>,
  );
}

describe("<NotesSection />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });
  afterEach(() => {
    mock.restore();
  });

  it("lists existing notes", async () => {
    setUser("owner");
    mock
      .onGet(/\/api\/v1\/notes/)
      .reply(200, { items: [aNote({ id: "n-1", body: "first" })] });
    renderSection();
    expect(await screen.findByTestId("note-n-1")).toBeInTheDocument();
    // Markdown rendered -> body text visible.
    expect(screen.getByText("first")).toBeInTheDocument();
  });

  it("composer posts a new note", async () => {
    setUser("production");
    let getCount = 0;
    mock.onGet(/\/api\/v1\/notes/).reply(() => {
      getCount += 1;
      return [
        200,
        {
          items:
            getCount > 1
              ? [aNote({ id: "n-new", body: "fresh note" })]
              : [],
        },
      ];
    });
    let posted = "";
    mock.onPost("/api/v1/notes").reply((cfg) => {
      posted = JSON.parse(cfg.data).body;
      return [201, aNote({ id: "n-new", body: posted })];
    });

    renderSection();
    await waitFor(() => {
      expect(screen.getByTestId("note-composer")).toBeInTheDocument();
    });
    const textarea = screen.getByTestId("note-composer-body");
    await userEvent.type(textarea, "fresh note");
    await userEvent.click(screen.getByTestId("note-submit"));
    await waitFor(() => {
      expect(posted).toBe("fresh note");
    });
  });

  it("author can enter edit mode for own note", async () => {
    setUser("production");
    mock
      .onGet(/\/api\/v1\/notes/)
      .reply(200, { items: [aNote({ id: "n-mine", body: "mine" })] });
    renderSection();
    await screen.findByTestId("note-n-mine");
    await userEvent.click(screen.getByTestId("edit-n-mine"));
    expect(screen.getByTestId("edit-body-n-mine")).toBeInTheDocument();
  });

  it("owner sees pin button on every note", async () => {
    setUser("owner");
    mock.onGet(/\/api\/v1\/notes/).reply(200, {
      items: [aNote({ id: "n-other", author_user_id: "someone-else" })],
    });
    renderSection();
    await screen.findByTestId("note-n-other");
    expect(screen.getByTestId("pin-n-other")).toBeInTheDocument();
  });

  it("non-owner does not see the pin button", async () => {
    setUser("production");
    mock.onGet(/\/api\/v1\/notes/).reply(200, {
      items: [aNote({ id: "n-other", author_user_id: "someone-else" })],
    });
    renderSection();
    await screen.findByTestId("note-n-other");
    expect(screen.queryByTestId("pin-n-other")).not.toBeInTheDocument();
    // Also: non-author non-owner sees no edit/delete buttons.
    expect(screen.queryByTestId("edit-n-other")).not.toBeInTheDocument();
  });
});
