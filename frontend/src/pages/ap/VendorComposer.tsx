/**
 * `/vendors/new` and `/vendors/:id/edit` — vendor composer. Mirrors
 * CustomerComposer with billing + shipping address sub-cards, 1099 flag,
 * tax id, default expense + AP account pickers, and a contacts sub-form.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type VendorResponse = components["schemas"]["VendorResponse"];
type VendorCreate = components["schemas"]["VendorCreate"];
type VendorUpdate = components["schemas"]["VendorUpdate"];
type VendorAddress = components["schemas"]["VendorAddress"];
type VendorContactCreate = components["schemas"]["VendorContactCreate"];

interface ContactDraft {
  id?: string;
  name: string;
  email: string;
  phone: string;
  role_label: string;
  is_primary: boolean;
}

function emptyContact(): ContactDraft {
  return { name: "", email: "", phone: "", role_label: "", is_primary: false };
}

function emptyAddress(): VendorAddress {
  return {
    line1: null,
    line2: null,
    city: null,
    region: null,
    postal_code: null,
    country: null,
  };
}

export function VendorComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [displayName, setDisplayName] = useState("");
  const [legalName, setLegalName] = useState("");
  const [primaryEmail, setPrimaryEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [paymentTermsDays, setPaymentTermsDays] = useState("30");
  const [taxId, setTaxId] = useState("");
  const [is1099, setIs1099] = useState(false);
  const [defaultExpenseAccountId, setDefaultExpenseAccountId] = useState("");
  const [defaultApAccountId, setDefaultApAccountId] = useState("");
  const [billing, setBilling] = useState<VendorAddress>(emptyAddress());
  const [shipping, setShipping] = useState<VendorAddress>(emptyAddress());
  const [notes, setNotes] = useState("");
  const [contacts, setContacts] = useState<ContactDraft[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .get(`/api/v1/vendors/${id}` as "/api/v1/vendors/{vendor_id}")
      .then((res) => {
        const v = res.data as unknown as VendorResponse;
        setDisplayName(v.display_name);
        setLegalName(v.legal_name ?? "");
        setPrimaryEmail(v.primary_email ?? "");
        setPhone(v.phone ?? "");
        setPaymentTermsDays(String(v.payment_terms_days));
        setTaxId(v.tax_id ?? "");
        setIs1099(v.is_1099_vendor);
        setDefaultExpenseAccountId(v.default_expense_account_id ?? "");
        setDefaultApAccountId(v.default_ap_account_id ?? "");
        setBilling(v.billing_address ?? emptyAddress());
        setShipping(v.shipping_address ?? emptyAddress());
        setNotes(v.notes ?? "");
        setContacts(
          (v.contacts ?? []).map((ct) => ({
            id: ct.id,
            name: ct.name,
            email: ct.email ?? "",
            phone: ct.phone ?? "",
            role_label: ct.role_label ?? "",
            is_primary: ct.is_primary,
          })),
        );
      })
      .catch(() => setError("Could not load vendor."));
  }, [id]);

  function updateContact(idx: number, patch: Partial<ContactDraft>) {
    setContacts((prev) =>
      prev.map((c, i) => (i === idx ? { ...c, ...patch } : c)),
    );
  }

  function setPrimary(idx: number) {
    setContacts((prev) =>
      prev.map((c, i) => ({ ...c, is_primary: i === idx })),
    );
  }

  async function submit() {
    if (!displayName.trim()) {
      setError("Display name is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      let vendorId: string;
      const termsNum = Number.parseInt(paymentTermsDays, 10) || 30;
      if (isEdit && id) {
        const body: VendorUpdate = {
          display_name: displayName,
          legal_name: legalName.trim() || null,
          primary_email: primaryEmail.trim() || null,
          phone: phone.trim() || null,
          payment_terms_days: termsNum,
          tax_id: taxId.trim() || null,
          is_1099_vendor: is1099,
          default_expense_account_id: defaultExpenseAccountId || null,
          default_ap_account_id: defaultApAccountId || null,
          billing_address: billing,
          shipping_address: shipping,
          notes: notes.trim() || null,
        };
        await apiClient.patch(`/api/v1/vendors/${id}`, body);
        vendorId = id;
        for (const c of contacts) {
          if (!c.name.trim()) continue;
          if (c.id) {
            await apiClient.patch(
              `/api/v1/vendors/${vendorId}/contacts/${c.id}`,
              {
                name: c.name,
                email: c.email.trim() || null,
                phone: c.phone.trim() || null,
                role_label: c.role_label.trim() || null,
                is_primary: c.is_primary,
              },
            );
          } else {
            const body: VendorContactCreate = {
              name: c.name,
              email: c.email.trim() || null,
              phone: c.phone.trim() || null,
              role_label: c.role_label.trim() || null,
              is_primary: c.is_primary,
            };
            await apiClient.post(`/api/v1/vendors/${vendorId}/contacts`, body);
          }
        }
      } else {
        const body: VendorCreate = {
          display_name: displayName,
          payment_terms_days: termsNum,
          is_1099_vendor: is1099,
        };
        if (legalName.trim()) body.legal_name = legalName.trim();
        if (primaryEmail.trim()) body.primary_email = primaryEmail.trim();
        if (phone.trim()) body.phone = phone.trim();
        if (taxId.trim()) body.tax_id = taxId.trim();
        if (defaultExpenseAccountId) {
          body.default_expense_account_id = defaultExpenseAccountId;
        }
        if (defaultApAccountId) {
          body.default_ap_account_id = defaultApAccountId;
        }
        body.billing_address = billing;
        body.shipping_address = shipping;
        if (notes.trim()) body.notes = notes.trim();
        const res = await apiClient.post<VendorResponse>(
          "/api/v1/vendors",
          body,
        );
        vendorId = res.data.id;
        for (const c of contacts) {
          if (!c.name.trim()) continue;
          const contactBody: VendorContactCreate = {
            name: c.name,
            email: c.email.trim() || null,
            phone: c.phone.trim() || null,
            role_label: c.role_label.trim() || null,
            is_primary: c.is_primary,
          };
          await apiClient.post(
            `/api/v1/vendors/${vendorId}/contacts`,
            contactBody,
          );
        }
      }
      navigate(`/vendors/${vendorId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save vendor.");
    } finally {
      setSubmitting(false);
    }
  }

  function addrField(
    label: string,
    addr: VendorAddress,
    setAddr: (a: VendorAddress) => void,
    key: keyof VendorAddress,
    prefix: string,
  ) {
    return (
      <label className="block text-sm">
        {label}
        <Input
          value={addr[key] ?? ""}
          onChange={(e) => setAddr({ ...addr, [key]: e.target.value || null })}
          data-testid={`${prefix}-${String(key)}`}
        />
      </label>
    );
  }

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">
          {isEdit ? "Edit vendor" : "New vendor"}
        </h1>
      </header>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Header</h2>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            Display name
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              data-testid="vendor-display-name"
            />
          </label>
          <label className="block text-sm">
            Legal name
            <Input
              value={legalName}
              onChange={(e) => setLegalName(e.target.value)}
              data-testid="vendor-legal-name"
            />
          </label>
          <label className="block text-sm">
            Primary email
            <Input
              type="email"
              value={primaryEmail}
              onChange={(e) => setPrimaryEmail(e.target.value)}
              data-testid="vendor-primary-email"
            />
          </label>
          <label className="block text-sm">
            Phone
            <Input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              data-testid="vendor-phone"
            />
          </label>
          <label className="block text-sm">
            Payment terms (days)
            <Input
              type="number"
              min={0}
              value={paymentTermsDays}
              onChange={(e) => setPaymentTermsDays(e.target.value)}
              data-testid="vendor-terms"
            />
          </label>
          <label className="block text-sm">
            Tax ID
            <Input
              value={taxId}
              onChange={(e) => setTaxId(e.target.value)}
              data-testid="vendor-tax-id"
            />
          </label>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={is1099}
            onChange={(e) => setIs1099(e.target.checked)}
            data-testid="vendor-is-1099"
          />
          1099 vendor
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            Default expense account
            <AccountPicker
              value={defaultExpenseAccountId}
              onChange={setDefaultExpenseAccountId}
              filterType="expense"
              data-testid="vendor-default-expense"
            />
          </label>
          <label className="block text-sm">
            Default AP account
            <AccountPicker
              value={defaultApAccountId}
              onChange={setDefaultApAccountId}
              filterType="liability"
              data-testid="vendor-default-ap"
            />
          </label>
        </div>

        <label className="block text-sm">
          Notes
          <textarea
            className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="vendor-notes"
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Billing address</h2>
          {addrField("Line 1", billing, setBilling, "line1", "billing")}
          {addrField("Line 2", billing, setBilling, "line2", "billing")}
          <div className="grid grid-cols-2 gap-2">
            {addrField("City", billing, setBilling, "city", "billing")}
            {addrField("Region", billing, setBilling, "region", "billing")}
            {addrField("Postal code", billing, setBilling, "postal_code", "billing")}
            {addrField("Country", billing, setBilling, "country", "billing")}
          </div>
        </div>
        <div className="space-y-2 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Shipping address</h2>
          {addrField("Line 1", shipping, setShipping, "line1", "shipping")}
          {addrField("Line 2", shipping, setShipping, "line2", "shipping")}
          <div className="grid grid-cols-2 gap-2">
            {addrField("City", shipping, setShipping, "city", "shipping")}
            {addrField("Region", shipping, setShipping, "region", "shipping")}
            {addrField("Postal code", shipping, setShipping, "postal_code", "shipping")}
            {addrField("Country", shipping, setShipping, "country", "shipping")}
          </div>
        </div>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Contacts</h2>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setContacts((p) => [...p, emptyContact()])}
            data-testid="add-contact-btn"
          >
            Add contact
          </Button>
        </div>
        {contacts.length === 0 ? (
          <p className="text-xs text-muted-foreground">No contacts.</p>
        ) : null}
        {contacts.map((c, idx) => (
          <div
            key={c.id ?? idx}
            className="space-y-2 rounded-md border border-border/60 p-2"
            data-testid={`contact-row-${idx}`}
          >
            <div className="grid grid-cols-2 gap-2">
              <Input
                value={c.name}
                placeholder="Name"
                onChange={(e) => updateContact(idx, { name: e.target.value })}
                data-testid={`contact-${idx}-name`}
              />
              <Input
                value={c.role_label}
                placeholder="Role"
                onChange={(e) =>
                  updateContact(idx, { role_label: e.target.value })
                }
                data-testid={`contact-${idx}-role`}
              />
              <Input
                type="email"
                value={c.email}
                placeholder="Email"
                onChange={(e) => updateContact(idx, { email: e.target.value })}
                data-testid={`contact-${idx}-email`}
              />
              <Input
                value={c.phone}
                placeholder="Phone"
                onChange={(e) => updateContact(idx, { phone: e.target.value })}
                data-testid={`contact-${idx}-phone`}
              />
            </div>
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="radio"
                  name="primary-vendor-contact"
                  checked={c.is_primary}
                  onChange={() => setPrimary(idx)}
                  data-testid={`contact-${idx}-primary`}
                />
                Primary
              </label>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() =>
                  setContacts((p) => p.filter((_, i) => i !== idx))
                }
                data-testid={`remove-contact-${idx}`}
              >
                Remove
              </Button>
            </div>
          </div>
        ))}
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button
          disabled={submitting}
          onClick={() => void submit()}
          data-testid="vendor-save"
        >
          {submitting ? "Saving…" : isEdit ? "Save changes" : "Create vendor"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/vendors")}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
