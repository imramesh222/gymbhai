"use client";

import { Copy, Pencil, Plus, XCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { ExpenseDialog, categoryLabel } from "@/components/money/ExpenseDialog";
import { methodLabel } from "@/components/money/PaymentFields";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Select, TextArea } from "@/components/ui/inputs";
import { Menu } from "@/components/ui/Menu";
import { Money } from "@/components/ui/Money";
import { MonthSwitcher } from "@/components/ui/MonthSwitcher";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import {
  branchesApi,
  EXPENSE_CATEGORIES,
  errorMessage,
  expensesApi,
  type Expense,
  type ExpenseCategory,
  type ExpenseInput,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useGymCalendar } from "@/lib/gym";
import { useIdempotencyKey } from "@/lib/idempotency";
import { useLive } from "@/lib/live";
import { formatRs } from "@/lib/money";
import { useLoad } from "@/lib/useLoad";

type Editing = { mode: "add" | "again" | "edit"; from: Expense | null };

/**
 * What the gym spent, a month at a time (PLAN.md §18.1). The list and its
 * totals are for staff who see money: salaries are in it. Anyone who may
 * record expenses gets the form.
 */
export default function ExpensesPage() {
  const { can, me } = useAuth();
  const toast = useToast();
  const { date, display } = useGymCalendar();
  const sees = can("reports.money");
  const records = can("expenses.record");
  const edits = can("expenses.edit");
  const [month, setMonth] = useState<string | undefined>(undefined);
  const [category, setCategory] = useState<ExpenseCategory | "">("");
  // Search (Ctrl/⌘K) opens this page with ?add=1.
  const wanted = useSearchParams().get("add") === "1";
  const [editing, setEditing] = useState<Editing | null>(
    wanted && records ? { mode: "add", from: null } : null,
  );
  const [voiding, setVoiding] = useState<Expense | null>(null);
  const keys = useIdempotencyKey();

  const list = useLoad(
    () =>
      sees
        ? expensesApi.list({ month, category: category || undefined })
        : Promise.resolve(null),
    [sees, month, category],
  );
  const { data: branches } = useLoad(() => branchesApi.list(), []);
  useLive(["expense"], list.reload);
  const data = list.data;
  const branchName = (id: string | null) =>
    id ? (branches?.find((b) => b.id === id)?.name ?? "") : t("expenses.wholeGym");
  const manyBranches = (branches?.length ?? 0) > 1;
  const wholeGym = me?.branch_ids == null;

  async function save(body: ExpenseInput, reason: string | null) {
    if (!editing) return;
    if (editing.mode === "edit" && editing.from) {
      await expensesApi.update(editing.from.id, { ...body, reason });
      toast.success(t("common.saved"));
    } else {
      const saved = await expensesApi.create(body, keys.keyFor(body));
      keys.succeeded();
      toast.success(t("expenses.recorded", { amount: formatRs(saved.amount) }));
    }
    setEditing(null);
    list.reload();
  }

  const add = records && (
    <Button onClick={() => setEditing({ mode: "add", from: null })}>
      <Plus className="size-4" aria-hidden />
      {t("expenses.add")}
    </Button>
  );
  const byCategory = Object.entries(data?.by_category ?? {}).sort(
    ([, a], [, b]) => b - a,
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("expenses.title")}
        subtitle={data ? `${date(data.first_day)} → ${date(data.last_day)}` : undefined}
        actions={add}
      />
      {!sees &&
        (records ? (
          <Notice>{t("expenses.recordOnly")}</Notice>
        ) : (
          <Notice tone="error">{t("errors.permission_denied")}</Notice>
        ))}
      {list.error && <Notice tone="error">{list.error}</Notice>}
      {sees && data && (
        <>
          <MonthSwitcher
            month={data.month}
            calendar={data.calendar}
            onChange={setMonth}
          />
          <div className="grid gap-3 sm:grid-cols-3">
            <Select<ExpenseCategory | "all">
              label={t("expenses.category")}
              value={category || "all"}
              onChange={(value) => setCategory(value === "all" ? "" : value)}
              options={[
                { value: "all", label: t("expenses.allCategories") },
                ...EXPENSE_CATEGORIES.map((c) => ({
                  value: c,
                  label: categoryLabel(c),
                })),
              ]}
            />
          </div>
          <Card>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
                  {t("expenses.spent")}
                </p>
                <Money
                  paisa={data.sum_amount}
                  className="text-3xl font-bold tracking-tight text-slate-900"
                />
              </div>
              {byCategory.length > 0 && (
                <dl
                  className="flex flex-wrap gap-4 text-sm"
                  aria-label={t("expenses.byCategory")}
                >
                  {byCategory.map(([c, amount]) => (
                    <div key={c}>
                      <dt className="text-xs text-slate-500">{categoryLabel(c)}</dt>
                      <dd className="font-semibold">
                        <Money paisa={amount} />
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          </Card>
          <Card title={t("expenses.count", { count: data.items.length })}>
            {data.items.length === 0 && (
              <EmptyState
                title={t("expenses.none")}
                hint={t("expenses.noneHint")}
                action={add}
              />
            )}
            <ul className="divide-y divide-hairline">
              {data.items.map((e) => {
                const voided = Boolean(e.voided_at);
                return (
                  <li
                    key={e.id}
                    className="flex items-center justify-between gap-3 py-2.5 text-sm"
                  >
                    <div className={`min-w-0 ${voided ? "text-slate-500" : ""}`}>
                      <p
                        className={`font-medium text-slate-900 ${voided ? "line-through" : ""}`}
                      >
                        {categoryLabel(e.category)}
                        {e.paid_to && ` · ${e.paid_to}`}
                      </p>
                      <p className="text-xs text-slate-500">
                        {date(e.spent_on)} · {methodLabel(e.method)}
                        {manyBranches && ` · ${branchName(e.branch_id)}`}
                        {e.created_by_name &&
                          ` · ${t("expenses.recordedBy", { name: e.created_by_name })}`}
                      </p>
                      {e.note && <p className="text-xs text-slate-600">{e.note}</p>}
                      {voided && e.void_reason && (
                        <p className="text-xs text-red-600">
                          {t("payment.voidedBecause", { reason: e.void_reason })}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Money
                        paisa={e.amount}
                        className={`font-semibold ${voided ? "text-slate-500 line-through" : ""}`}
                      />
                      <Menu
                        compact
                        items={[
                          {
                            label: t("common.edit"),
                            icon: Pencil,
                            hidden: !edits || voided,
                            onSelect: () => setEditing({ mode: "edit", from: e }),
                          },
                          {
                            label: t("expenses.again"),
                            icon: Copy,
                            hidden: !records,
                            onSelect: () => setEditing({ mode: "again", from: e }),
                          },
                          {
                            label: t("expenses.void"),
                            icon: XCircle,
                            danger: true,
                            hidden: !edits || voided,
                            onSelect: () => setVoiding(e),
                          },
                        ]}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>
        </>
      )}

      {editing && (
        <ExpenseDialog
          title={editing.mode === "edit" ? t("expenses.edit") : t("expenses.add")}
          from={editing.from}
          editing={editing.mode === "edit"}
          branches={branches ?? []}
          wholeGym={wholeGym}
          display={display}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}
      {voiding && (
        <VoidDialog
          onClose={() => setVoiding(null)}
          onVoid={async (reason) => {
            await expensesApi.void(voiding.id, reason);
            toast.success(t("expenses.voided"));
            setVoiding(null);
            list.reload();
          }}
        />
      )}
    </div>
  );
}

function VoidDialog({
  onClose,
  onVoid,
}: {
  onClose: () => void;
  onVoid: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  return (
    <Dialog open onClose={onClose} title={t("expenses.void")}>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (saving) return;
          setSaving(true);
          setError(null);
          try {
            await onVoid(reason);
          } catch (err) {
            setError(errorMessage(err));
            setSaving(false);
          }
        }}
        className="space-y-3"
      >
        <TextArea
          label={t("membership.reason")}
          value={reason}
          onChange={setReason}
          required
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" variant="danger" block disabled={saving}>
          {t("expenses.void")}
        </Button>
      </form>
    </Dialog>
  );
}
