"use client";

import { History, PackagePlus, Pencil, Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Form } from "@/components/Form";
import { Notice } from "@/components/Notice";
import { Card, EmptyState } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox, MoneyInput, Select } from "@/components/ui/inputs";
import { Menu } from "@/components/ui/Menu";
import { Money } from "@/components/ui/Money";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, shopApi, type Product, type ProductCategory } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

import { CATEGORIES, categoryLabel, stockLabel } from "./Till";

/** Products and their stock (PLAN.md §20.1), for staff with Products and stock. */
export function Products({
  products,
  onChanged,
}: {
  products: Product[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const [stocking, setStocking] = useState<Product | null>(null);
  const [history, setHistory] = useState<Product | null>(null);
  return (
    <Card
      title={t("shop.products")}
      actions={
        <Button onClick={() => setEditing("new")}>
          <Plus className="size-4" aria-hidden />
          {t("shop.addProduct")}
        </Button>
      }
    >
      {products.length === 0 && (
        <EmptyState title={t("shop.noProducts")} hint={t("shop.noProductsHint")} />
      )}
      <ul className="divide-y divide-hairline">
        {products.map((product) => {
          const left = stockLabel(product);
          const low =
            product.stock !== null &&
            product.low_stock !== null &&
            product.stock <= product.low_stock;
          return (
            <li
              key={product.id}
              className="flex items-center justify-between gap-3 py-2.5 text-sm"
            >
              <div className="min-w-0">
                <p
                  className={`font-medium ${product.is_active ? "text-slate-900" : "text-slate-500"}`}
                >
                  {product.name}
                  {!product.is_active && ` · ${t("plans.hidden")}`}
                </p>
                <p className="text-xs text-slate-500">
                  {categoryLabel(product.category)}
                  {product.code && ` · ${product.code}`}
                  {left && (
                    <span className={low ? "font-semibold text-amber-700" : ""}>
                      {" · "}
                      {left}
                    </span>
                  )}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Money paisa={product.price} className="font-semibold" />
                <Menu
                  compact
                  items={[
                    {
                      label: t("common.edit"),
                      icon: Pencil,
                      onSelect: () => setEditing(product),
                    },
                    {
                      label: t("shop.stock"),
                      icon: PackagePlus,
                      onSelect: () => setStocking(product),
                    },
                    {
                      label: t("shop.stockHistory"),
                      icon: History,
                      hidden: product.stock === null,
                      onSelect: () => setHistory(product),
                    },
                  ]}
                />
              </div>
            </li>
          );
        })}
      </ul>
      {editing && (
        <ProductDialog
          product={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
      {stocking && (
        <StockDialog
          product={stocking}
          onClose={() => setStocking(null)}
          onSaved={() => {
            setStocking(null);
            onChanged();
          }}
        />
      )}
      {history && <StockHistory product={history} onClose={() => setHistory(null)} />}
    </Card>
  );
}

function ProductDialog({
  product,
  onClose,
  onSaved,
}: {
  product: Product | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState({
    name: product?.name ?? "",
    category: product?.category ?? ("supplement" as ProductCategory),
    price: product?.price ?? null,
    code: product?.code ?? "",
    counted: product ? product.stock !== null : true,
    stock: "",
    low_stock: product?.low_stock?.toString() ?? "",
    is_active: product?.is_active ?? true,
  });
  const [error, setError] = useState<string | null>(null);
  const number = (value: string) => (value.trim() === "" ? null : Number(value));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (form.price === null) return setError(t("shop.needPrice"));
    const body = {
      name: form.name,
      category: form.category,
      price: form.price,
      code: form.code.trim() || null,
      low_stock: form.counted ? number(form.low_stock) : null,
    };
    try {
      if (product) {
        await shopApi.updateProduct(product.id, {
          ...body,
          is_active: form.is_active,
          track_stock: form.counted,
        });
      } else {
        await shopApi.createProduct({
          ...body,
          stock: form.counted ? (number(form.stock) ?? 0) : null,
        });
      }
      toast.success(t("common.saved"));
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={product ? t("shop.editProduct") : t("shop.addProduct")}
    >
      <Form onSubmit={save} className="space-y-3">
        <Field
          label={t("shop.name")}
          value={form.name}
          onChange={(name) => setForm({ ...form, name })}
          required
        />
        <div className="grid grid-cols-2 gap-3">
          <Select<ProductCategory>
            label={t("shop.category")}
            value={form.category}
            onChange={(category) => setForm({ ...form, category })}
            options={CATEGORIES.map((c) => ({ value: c, label: categoryLabel(c) }))}
          />
          <MoneyInput
            label={t("sale.price")}
            value={form.price}
            onChange={(price) => setForm({ ...form, price })}
            required
          />
        </div>
        <Field
          label={t("shop.code")}
          value={form.code}
          onChange={(code) => setForm({ ...form, code })}
          help={t("shop.codeHelp")}
          optional
          optionalLabel={t("common.optional")}
        />
        <Checkbox
          label={t("shop.counted")}
          hint={t("shop.countedHelp")}
          checked={form.counted}
          onChange={(counted) => setForm({ ...form, counted })}
        />
        {form.counted && (
          <div className="grid grid-cols-2 gap-3">
            {!product && (
              <Field
                label={t("shop.openingStock")}
                value={form.stock}
                onChange={(stock) => setForm({ ...form, stock })}
                type="number"
                inputMode="numeric"
              />
            )}
            <Field
              label={t("shop.lowStock")}
              value={form.low_stock}
              onChange={(low_stock) => setForm({ ...form, low_stock })}
              type="number"
              inputMode="numeric"
              optional
              optionalLabel={t("common.optional")}
            />
          </div>
        )}
        {product && (
          <Checkbox
            label={t("shop.onSale")}
            checked={form.is_active}
            onChange={(is_active) => setForm({ ...form, is_active })}
          />
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
      </Form>
    </Dialog>
  );
}

function StockDialog({
  product,
  onClose,
  onSaved,
}: {
  product: Product;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [kind, setKind] = useState<"restock" | "count">("restock");
  const [quantity, setQuantity] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog open onClose={onClose} title={t("shop.stockOf", { name: product.name })}>
      <Form
        className="space-y-3"
        onSubmit={async (event) => {
          event.preventDefault();
          try {
            const saved = await shopApi.changeStock(product.id, {
              kind,
              quantity: Number(quantity),
              note: note.trim() || null,
            });
            toast.success(t("shop.stockNow", { count: saved.stock ?? 0 }));
            onSaved();
          } catch (err) {
            setError(errorMessage(err));
          }
        }}
      >
        {product.stock !== null && (
          <p className="text-sm text-slate-600">
            {t("shop.stockIs", { count: product.stock })}
          </p>
        )}
        <Select<"restock" | "count">
          label={t("shop.stockKind")}
          value={kind}
          onChange={setKind}
          options={[
            { value: "restock", label: t("shop.restock") },
            { value: "count", label: t("shop.count") },
          ]}
        />
        <Field
          label={kind === "restock" ? t("shop.arrived") : t("shop.onShelf")}
          value={quantity}
          onChange={setQuantity}
          type="number"
          inputMode="numeric"
          required
        />
        <Field
          label={t("progress.note")}
          value={note}
          onChange={setNote}
          optional
          optionalLabel={t("common.optional")}
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
      </Form>
    </Dialog>
  );
}

function StockHistory({ product, onClose }: { product: Product; onClose: () => void }) {
  const { display } = useGymCalendar();
  const { data, error } = useLoad(() => shopApi.stockHistory(product.id), [product.id]);
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("shop.stockHistoryOf", { name: product.name })}
    >
      {error && <Notice tone="error">{error}</Notice>}
      <ul className="divide-y divide-hairline text-sm">
        {data?.map((move) => (
          <li key={move.id} className="flex justify-between gap-3 py-2">
            <span>
              {t(`shop.move.${move.reason}` as MessageKey)}
              <span className="block text-xs text-slate-500">
                {formatDateTime(move.created_at, display)}
                {move.created_by_name && ` · ${move.created_by_name}`}
                {move.note && ` · ${move.note}`}
              </span>
            </span>
            <span
              className={`font-semibold tabular-nums ${move.change < 0 ? "text-slate-700" : "text-emerald-700"}`}
            >
              {move.change > 0 ? `+${move.change}` : move.change}
            </span>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}
