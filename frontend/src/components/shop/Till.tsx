"use client";

import { Minus, Plus, ShoppingBag, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { MemberPicker, type Picked } from "@/components/member/MemberPicker";
import { METHODS, methodLabel } from "@/components/money/PaymentFields";
import { Notice } from "@/components/Notice";
import { Card, EmptyState } from "@/components/ui/Card";
import { MoneyInput, Select } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import {
  errorMessage,
  shopApi,
  type Method,
  type Product,
  type ProductCategory,
} from "@/lib/api";
import { useIdempotencyKey } from "@/lib/idempotency";

export const CATEGORIES: ProductCategory[] = [
  "supplement",
  "drink",
  "snack",
  "merchandise",
  "other",
];

export function categoryLabel(category: string): string {
  return t(`shop.category.${category}` as MessageKey);
}

/** "8 left", "Out of stock", or nothing for a product nobody counts. */
export function stockLabel(product: Product): string | null {
  if (product.stock === null) return null;
  if (product.stock <= 0) return t("shop.outOfStock");
  return t("shop.left", { count: product.stock });
}

/**
 * The till (PLAN.md §20.1): tap products into the basket, for a member or a
 * walk-in, take the money, and the receipt is ready. One tap is one sale.
 */
export function Till({
  products,
  onSold,
}: {
  products: Product[];
  onSold: () => void;
}) {
  const toast = useToast();
  const router = useRouter();
  const [basket, setBasket] = useState<Record<string, number>>({});
  const [member, setMember] = useState<Picked | null>(null);
  const [method, setMethod] = useState<Method>("cash");
  const [reference, setReference] = useState("");
  const [discount, setDiscount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selling, setSelling] = useState(false);
  const [code, setCode] = useState("");
  const saving = useIdempotencyKey();

  const byId = useMemo(() => new Map(products.map((p) => [p.id, p])), [products]);
  const lines = Object.entries(basket)
    .map(([id, quantity]) => ({ product: byId.get(id), quantity }))
    .filter((line): line is { product: Product; quantity: number } =>
      Boolean(line.product),
    );
  const subtotal = lines.reduce((sum, l) => sum + l.product.price * l.quantity, 0);
  const total = Math.max(0, subtotal - (discount ?? 0));

  function add(product: Product, change = 1) {
    setError(null);
    setBasket((now) => {
      const next = Math.max(0, (now[product.id] ?? 0) + change);
      const capped = product.stock === null ? next : Math.min(next, product.stock);
      const rest = { ...now };
      if (capped === 0) delete rest[product.id];
      else rest[product.id] = capped;
      return rest;
    });
  }

  async function sell() {
    if (selling || lines.length === 0) return;
    setSelling(true);
    setError(null);
    const body = {
      lines: lines.map((l) => ({ product_id: l.product.id, quantity: l.quantity })),
      member_id: member?.id ?? null,
      discount: discount ?? 0,
      payment: {
        method,
        transaction_ref: method === "cash" ? null : reference.trim() || null,
      },
    };
    try {
      const sold = await shopApi.sell(body, saving.keyFor(body));
      saving.succeeded();
      const receipt = sold.payment_id;
      toast.success(
        t("shop.sold", { receipt: sold.receipt_no ?? "" }),
        receipt
          ? {
              label: t("payment.receipt"),
              onClick: () => router.push(`/staff/receipts/${receipt}`),
            }
          : undefined,
      );
      setBasket({});
      setMember(null);
      setDiscount(null);
      setReference("");
      onSold();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSelling(false);
    }
  }

  const shown = CATEGORIES.map((c) => ({
    category: c,
    items: products.filter((p) => p.category === c),
  })).filter((group) => group.items.length > 0);

  if (products.length === 0)
    return (
      <EmptyState
        title={t("shop.noProducts")}
        hint={t("shop.noProductsHint")}
        action={
          <Link
            href="/staff/shop?tab=products"
            className="text-sm font-semibold text-brand-700"
          >
            {t("shop.addProduct")}
          </Link>
        }
      />
    );

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
      <div className="space-y-4">
        {/* A USB barcode scanner types here and presses Enter. */}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const found = products.find((p) => p.code && p.code === code.trim());
            if (found) add(found);
            else if (code.trim()) setError(t("shop.noSuchCode"));
            setCode("");
          }}
        >
          <Field
            label={t("shop.scanCode")}
            value={code}
            onChange={setCode}
            inputMode="numeric"
            autoComplete="off"
          />
        </form>
        {shown.map(({ category, items }) => (
          <Card key={category} title={categoryLabel(category)}>
            <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {items.map((product) => {
                const left = stockLabel(product);
                const out = product.stock !== null && product.stock <= 0;
                const low =
                  product.stock !== null &&
                  product.low_stock !== null &&
                  product.stock <= product.low_stock;
                return (
                  <li key={product.id}>
                    <button
                      type="button"
                      disabled={out}
                      onClick={() => add(product)}
                      className="flex w-full items-center justify-between gap-2 rounded-xl p-3 text-left ring-1 ring-hairline hover:bg-slate-50 disabled:opacity-50"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium">
                          {product.name}
                        </span>
                        {left && (
                          <span
                            className={`block text-xs ${low || out ? "text-amber-700" : "text-slate-500"}`}
                          >
                            {left}
                          </span>
                        )}
                      </span>
                      <Money paisa={product.price} className="shrink-0 font-semibold" />
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>
        ))}
      </div>

      <Card title={t("shop.basket")}>
        <div className="space-y-3">
          {lines.length === 0 ? (
            <p className="flex items-center gap-2 text-sm text-slate-500">
              <ShoppingBag className="size-4" aria-hidden />
              {t("shop.basketEmpty")}
            </p>
          ) : (
            <ul className="divide-y divide-hairline" aria-label={t("shop.basket")}>
              {lines.map(({ product, quantity }) => (
                <li key={product.id} className="flex items-center gap-2 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate">{product.name}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={t("shop.less", { name: product.name })}
                    onClick={() => add(product, -1)}
                  >
                    {quantity === 1 ? (
                      <Trash2 className="size-4" aria-hidden />
                    ) : (
                      <Minus className="size-4" aria-hidden />
                    )}
                  </Button>
                  <span className="w-6 text-center tabular-nums">{quantity}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={t("shop.more", { name: product.name })}
                    onClick={() => add(product)}
                  >
                    <Plus className="size-4" aria-hidden />
                  </Button>
                  <Money paisa={product.price * quantity} className="w-20 text-right" />
                </li>
              ))}
            </ul>
          )}
          <MemberPicker
            label={t("shop.forMember")}
            value={member}
            onChange={setMember}
          />
          <MoneyInput
            label={t("shop.discount")}
            value={discount}
            onChange={setDiscount}
          />
          <Select<Method>
            label={t("payment.method")}
            value={method}
            onChange={setMethod}
            options={METHODS.map((m) => ({ value: m, label: methodLabel(m) }))}
          />
          {method !== "cash" && (
            <Field
              label={t("payment.transactionRef")}
              value={reference}
              onChange={setReference}
              optional
              optionalLabel={t("common.optional")}
            />
          )}
          <div className="flex items-baseline justify-between border-t border-hairline pt-3">
            <span className="text-sm text-slate-600">{t("shop.total")}</span>
            <Money paisa={total} className="text-2xl font-bold" />
          </div>
          {error && <Notice tone="error">{error}</Notice>}
          <Button
            block
            onClick={() => void sell()}
            disabled={selling || lines.length === 0}
          >
            {selling ? t("common.saving") : t("shop.sell")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
