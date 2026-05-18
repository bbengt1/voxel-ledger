/**
 * Minimal CSV preview helper for the mapping composer. NOT a production
 * parser — embedded delimiters inside quoted fields are not handled. The
 * goal here is operator feedback: paste a few rows, see how the mapping
 * config interprets them.
 */

export interface MappingPreviewConfig {
  column_map: Record<string, string>;
  delimiter: string;
  has_header: boolean;
  date_format: string | null;
  amount_sign: string;
}

export interface ParsedRow {
  date: string;
  description: string;
  amount: string;
  memo: string;
  raw: Record<string, string>;
  errors: string[];
}

function splitLine(line: string, delim: string): string[] {
  // Naive split — good enough for live preview.
  return line.split(delim).map((s) => s.trim());
}

function parseDateLoose(value: string, fmt: string | null): string {
  // We support: %Y-%m-%d, %m/%d/%Y, %d/%m/%Y. Returns ISO yyyy-mm-dd, or
  // the original string on failure (the operator sees their config is off).
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (!fmt || fmt === "%Y-%m-%d") {
    return trimmed;
  }
  if (fmt === "%m/%d/%Y" || fmt === "%d/%m/%Y") {
    const parts = trimmed.split(/[/-]/);
    if (parts.length !== 3) return trimmed;
    const [a, b, c] = parts as [string, string, string];
    const year = c.padStart(4, "0");
    if (fmt === "%m/%d/%Y") {
      return `${year}-${a.padStart(2, "0")}-${b.padStart(2, "0")}`;
    }
    return `${year}-${b.padStart(2, "0")}-${a.padStart(2, "0")}`;
  }
  return trimmed;
}

function pick(
  raw: Record<string, string>,
  map: Record<string, string>,
  key: string,
): string {
  const col = map[key];
  if (!col) return "";
  return raw[col] ?? "";
}

function deriveAmount(
  raw: Record<string, string>,
  map: Record<string, string>,
  amountSign: string,
): { amount: string; error?: string } {
  if (amountSign === "signed_amount") {
    const v = pick(raw, map, "amount");
    return { amount: v };
  }
  if (amountSign === "debit_credit_columns") {
    const debit = pick(raw, map, "debit");
    const credit = pick(raw, map, "credit");
    const d = Number.parseFloat(debit || "0");
    const c = Number.parseFloat(credit || "0");
    if (Number.isNaN(d) || Number.isNaN(c)) {
      return { amount: "", error: "non-numeric debit/credit" };
    }
    // Bank convention: debit on a statement = money out (negative), credit
    // = money in (positive). Mirror what the server uses for previews.
    return { amount: (c - d).toFixed(2) };
  }
  if (amountSign === "inflow_outflow") {
    const inflow = pick(raw, map, "credit");
    const outflow = pick(raw, map, "debit");
    const inAmt = Number.parseFloat(inflow || "0");
    const outAmt = Number.parseFloat(outflow || "0");
    if (Number.isNaN(inAmt) || Number.isNaN(outAmt)) {
      return { amount: "", error: "non-numeric inflow/outflow" };
    }
    return { amount: (inAmt - outAmt).toFixed(2) };
  }
  return { amount: "" };
}

export function parseCsvPreview(
  text: string,
  config: MappingPreviewConfig,
  limit = 5,
): ParsedRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  if (lines.length === 0) return [];

  const delim = config.delimiter || ",";
  let headers: string[];
  let dataLines: string[];
  if (config.has_header) {
    const firstLine = lines[0] ?? "";
    headers = splitLine(firstLine, delim);
    dataLines = lines.slice(1);
  } else {
    const firstLine = lines[0] ?? "";
    headers = splitLine(firstLine, delim).map((_, i) => `col${i}`);
    dataLines = lines;
  }

  const out: ParsedRow[] = [];
  for (const line of dataLines.slice(0, limit)) {
    const cells = splitLine(line, delim);
    const raw: Record<string, string> = {};
    headers.forEach((h, idx) => {
      raw[h] = cells[idx] ?? "";
    });
    const errors: string[] = [];
    const dateRaw = pick(raw, config.column_map, "date");
    const date = parseDateLoose(dateRaw, config.date_format);
    const description = pick(raw, config.column_map, "description");
    const memo = pick(raw, config.column_map, "memo");
    const { amount, error } = deriveAmount(
      raw,
      config.column_map,
      config.amount_sign,
    );
    if (error) errors.push(error);
    out.push({ date, description, amount, memo, raw, errors });
  }
  return out;
}
