/**
 * Bank-account picker: reuses the AR AccountPicker filtered to assets.
 * Bank/cash accounts live under the asset type; this is a tiny wrapper so
 * callers don't have to repeat the filterType prop and so we have one
 * symbol to grep when banking-account UX changes.
 */
import { AccountPicker } from "@/components/ar/AccountPicker";

interface Props {
  value: string;
  onChange: (id: string) => void;
  id?: string;
  disabled?: boolean;
  placeholder?: string;
  "data-testid"?: string;
}

export function BankAccountPicker({
  value,
  onChange,
  id,
  disabled,
  placeholder,
  "data-testid": testId,
}: Props) {
  return (
    <AccountPicker
      value={value}
      onChange={onChange}
      filterType="asset"
      id={id}
      disabled={disabled}
      placeholder={placeholder ?? "— Pick a bank/cash account —"}
      data-testid={testId}
    />
  );
}
