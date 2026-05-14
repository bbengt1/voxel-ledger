import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { AttachmentsSection } from "@/components/platform/AttachmentsSection";
import { useAuthStore } from "@/store/useAuthStore";

const ENTITY_ID = "11111111-1111-1111-1111-111111111111";
const USER_ID = "u-1";

function setUser(role: "owner" | "production" | "viewer") {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: USER_ID, email: "u@example.com", role },
  });
}

function anAttachment(
  overrides: Partial<{
    id: string;
    filename: string;
    byte_size: number;
    uploaded_by_user_id: string;
    is_archived: boolean;
  }> = {},
) {
  return {
    id: "a-1",
    entity_kind: "material",
    entity_id: ENTITY_ID,
    filename: "doc.txt",
    mime_type: "text/plain",
    byte_size: 100,
    uploaded_by_user_id: USER_ID,
    is_archived: false,
    created_at: "2026-05-14T12:00:00Z",
    updated_at: "2026-05-14T12:00:00Z",
    ...overrides,
  };
}

function renderSection() {
  return render(
    <AppProviders>
      <AttachmentsSection entityKind="material" entityId={ENTITY_ID} />
    </AppProviders>,
  );
}

describe("<AttachmentsSection />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });
  afterEach(() => {
    mock.restore();
  });

  it("lists attachments with download link", async () => {
    setUser("owner");
    mock
      .onGet(/\/api\/v1\/attachments/)
      .reply(200, { items: [anAttachment({ id: "a-1", filename: "x.pdf" })] });
    renderSection();
    const link = await screen.findByTestId("download-a-1");
    expect(link).toHaveAttribute(
      "href",
      "/api/v1/attachments/a-1/download",
    );
    expect(link).toHaveTextContent("x.pdf");
  });

  it("uploads a file via the hidden input", async () => {
    setUser("production");
    let getCount = 0;
    mock.onGet(/\/api\/v1\/attachments/).reply(() => {
      getCount += 1;
      return [200, { items: getCount > 1 ? [anAttachment()] : [] }];
    });
    let posted = false;
    mock.onPost("/api/v1/attachments").reply(() => {
      posted = true;
      return [201, anAttachment()];
    });

    renderSection();
    await waitFor(() => {
      expect(screen.getByTestId("attachment-uploader")).toBeInTheDocument();
    });
    const input = screen.getByTestId(
      "attachment-file-input",
    ) as HTMLInputElement;
    const file = new File(["hello"], "note.txt", { type: "text/plain" });
    await userEvent.upload(input, file);
    await waitFor(() => {
      expect(posted).toBe(true);
    });
  });

  it("rejects oversize files client-side without posting", async () => {
    setUser("production");
    mock.onGet(/\/api\/v1\/attachments/).reply(200, { items: [] });
    let posted = false;
    mock.onPost("/api/v1/attachments").reply(() => {
      posted = true;
      return [201, anAttachment()];
    });

    renderSection();
    await waitFor(() => {
      expect(screen.getByTestId("attachment-uploader")).toBeInTheDocument();
    });
    // Stub a file whose size pretends to be 11MB (so we don't allocate
    // a real 11MB Blob in the test process).
    const file = new File(["x"], "big.bin", { type: "text/plain" });
    Object.defineProperty(file, "size", { value: 11 * 1024 * 1024 });
    const input = screen.getByTestId(
      "attachment-file-input",
    ) as HTMLInputElement;
    await userEvent.upload(input, file);
    expect(await screen.findByRole("alert")).toHaveTextContent(/too large/);
    expect(posted).toBe(false);
  });

  it("uploader can archive their own attachment", async () => {
    setUser("production");
    mock
      .onGet(/\/api\/v1\/attachments/)
      .reply(200, { items: [anAttachment({ id: "a-1" })] });
    let archived = false;
    mock.onPost("/api/v1/attachments/a-1/archive").reply(() => {
      archived = true;
      return [200, anAttachment({ id: "a-1", is_archived: true })];
    });
    renderSection();
    await screen.findByTestId("attachment-a-1");
    await userEvent.click(screen.getByTestId("archive-a-1"));
    await waitFor(() => {
      expect(archived).toBe(true);
    });
  });

  it("viewer sees no upload button", async () => {
    setUser("viewer");
    mock.onGet(/\/api\/v1\/attachments/).reply(200, { items: [] });
    renderSection();
    await waitFor(() => {
      expect(
        screen.queryByTestId("attachment-uploader"),
      ).not.toBeInTheDocument();
    });
  });
});
