/**
 * `/customers/new` and `/customers/:id` — customer composer.
 *
 * Header form (display + legal name, primary email/phone, payment terms,
 * default revenue / AR accounts, billing + shipping address) plus an
 * inline contacts sub-form (add / remove / set primary).
 *
 * On edit, contacts are persisted via the dedicated contacts endpoints so
 * the user can mutate them without losing the header diff.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type CustomerResponse = components["schemas"]["CustomerResponse"];
type CustomerCreate = components["schemas"]["CustomerCreate"];
type CustomerUpdate = components["schemas"]["CustomerUpdate"];
type CustomerAddress = components["schemas"]["CustomerAddress"];
type CustomerContactCreate = components["schemas"]["CustomerContactCreate"];

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

function emptyAddress(): CustomerAddress {
  return {
    line1: null,
    line2: null,
    city: null,
    region: null,
    postal_code: null,
    country: null,
  };
}

export function CustomerComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [displayName, setDisplayName] = useState("");
  const [legalName, setLegalName] = useState("");
  const [primaryEmail, setPrimaryEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [paymentTermsDays, setPaymentTermsDays] = useState("30");
  const [defaultRevenueAccountId, setDefaultRevenueAccountId] = useState("");
  const [defaultArAccountId, setDefaultArAccountId] = useState("");
  const [billing, setBilling] = useState<CustomerAddress>(emptyAddress());
  const [shipping, setShipping] = useState<CustomerAddress>(emptyAddress());
  const [notes, setNotes] = useState("");
  const [contacts, setContacts] = useState<ContactDraft[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .get(`/api/v1/customers/${id}` as "/api/v1/customers/{customer_id}")
      .then((res) => {
        const c = res.data as unknown as CustomerResponse;
        setDisplayName(c.display_name);
        setLegalName(c.legal_name ?? "");
        setPrimaryEmail(c.primary_email ?? "");
        setPhone(c.phone ?? "");
        setPaymentTermsDays(String(c.payment_terms_days));
        setDefaultRevenueAccountId(c.default_revenue_account_id ?? "");
        setDefaultArAccountId(c.default_ar_account_id ?? "");
        setBilling(c.billing_address ?? emptyAddress());
        setShipping(c.shipping_address ?? emptyAddress());
        setNotes(c.notes ?? "");
        setContacts(
          (c.contacts ?? []).map((ct) => ({
            id: ct.id,
            name: ct.name,
            email: ct.email ?? "",
            phone: ct.phone ?? "",
            role_label: ct.role_label ?? "",
            is_primary: ct.is_primary,
          })),
        );
      })
      .catch(() => setError("Could not load customer."));
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
      let customerId: string;
      const baseBody = {
        display_name: displayName,
        legal_name: legalName.trim() || null,
        primary_email: primaryEmail.trim() || null,
        phone: phone.trim() || null,
        payment_terms_days: Number.parseInt(paymentTermsDays, 10) || 30,
        default_revenue_account_id: defaultRevenueAccountId || null,
        default_ar_account_id: defaultArAccountId || null,
        billing_address: billing,
        shipping_address: shipping,
        notes: notes.trim() || null,
      };
      if (isEdit && id) {
        const body: CustomerUpdate = baseBody;
        await apiClient.patch(`/api/v1/customers/${id}`, body);
        customerId = id;
        for (const c of contacts) {
          if (!c.name.trim()) continue;
          if (c.id) {
            await apiClient.patch(
              `/api/v1/customers/${customerId}/contacts/${c.id}`,
              {
                name: c.name,
                email: c.email.trim() || null,
                phone: c.phone.trim() || null,
                role_label: c.role_label.trim() || null,
                is_primary: c.is_primary,
              },
            );
          } else {
            const body: CustomerContactCreate = {
              name: c.name,
              email: c.email.trim() || null,
              phone: c.phone.trim() || null,
              role_label: c.role_label.trim() || null,
              is_primary: c.is_primary,
            };
            await apiClient.post(
              `/api/v1/customers/${customerId}/contacts`,
              body,
            );
          }
        }
      } else {
        const body: CustomerCreate = {
          display_name: baseBody.display_name,
          payment_terms_days: baseBody.payment_terms_days,
        };
        if (baseBody.legal_name) body.legal_name = baseBody.legal_name;
        if (baseBody.primary_email) body.primary_email = baseBody.primary_email;
        if (baseBody.phone) body.phone = baseBody.phone;
        if (baseBody.default_revenue_account_id) {
          body.default_revenue_account_id = baseBody.default_revenue_account_id;
        }
        if (baseBody.default_ar_account_id) {
          body.default_ar_account_id = baseBody.default_ar_account_id;
        }
        body.billing_address = baseBody.billing_address;
        body.shipping_address = baseBody.shipping_address;
        if (baseBody.notes) body.notes = baseBody.notes;
        const res = await apiClient.post<CustomerResponse>(
          "/api/v1/customers",
          body,
        );
        customerId = res.data.id;
        for (const c of contacts) {
          if (!c.name.trim()) continue;
          const contactBody: CustomerContactCreate = {
            name: c.name,
            email: c.email.trim() || null,
            phone: c.phone.trim() || null,
            role_label: c.role_label.trim() || null,
            is_primary: c.is_primary,
          };
          await apiClient.post(
            `/api/v1/customers/${customerId}/contacts`,
            contactBody,
          );
        }
      }
      navigate(`/customers/${customerId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save customer.");
    } finally {
      setSubmitting(false);
    }
  }

  function addrField(
    label: string,
    addr: CustomerAddress,
    setAddr: (a: CustomerAddress) => void,
    key: keyof CustomerAddress,
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
          {isEdit ? "Edit customer" : "New customer"}
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
              data-testid="customer-display-name"
            />
          </label>
          <label className="block text-sm">
            Legal name
            <Input
              value={legalName}
              onChange={(e) => setLegalName(e.target.value)}
              data-testid="customer-legal-name"
            />
          </label>
          <label className="block text-sm">
            Primary email
            <Input
              type="email"
              value={primaryEmail}
              onChange={(e) => setPrimaryEmail(e.target.value)}
              data-testid="customer-primary-email"
            />
          </label>
          <label className="block text-sm">
            Phone
            <Input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              data-testid="customer-phone"
            />
          </label>
          <label className="block text-sm">
            Payment terms (days)
            <Input
              type="number"
              min={0}
              value={paymentTermsDays}
              onChange={(e) => setPaymentTermsDays(e.target.value)}
              data-testid="customer-terms"
            />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            Default revenue account
            <AccountPicker
              value={defaultRevenueAccountId}
              onChange={setDefaultRevenueAccountId}
              filterType="revenue"
              data-testid="customer-default-revenue"
            />
          </label>
          <label className="block text-sm">
            Default AR account
            <AccountPicker
              value={defaultArAccountId}
              onChange={setDefaultArAccountId}
              filterType="asset"
              data-testid="customer-default-ar"
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
            data-testid="customer-notes"
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
                  name="primary-contact"
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
          data-testid="customer-save"
        >
          {submitting ? "Saving…" : isEdit ? "Save changes" : "Create customer"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/customers")}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
