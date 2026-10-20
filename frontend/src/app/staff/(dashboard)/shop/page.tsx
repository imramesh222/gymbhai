"use client";

import { useState } from "react";

import { Notice } from "@/components/Notice";
import { Products } from "@/components/shop/Products";
import { SalesList } from "@/components/shop/SalesList";
import { Till } from "@/components/shop/Till";
import { PageHeader } from "@/components/ui/Card";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { Tabs, useTab } from "@/components/ui/Tabs";
import { t } from "@/i18n";
import { shopApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

/**
 * Desk → Shop (PLAN.md §20.1): sell supplements and drinks at the till, the
 * products and their stock, and a month of sales.
 */
export default function ShopPage() {
  const { can } = useAuth();
  const sells = can("shop.sell");
  const manages = can("shop.manage");
  const money = can("reports.money");
  const tabs = [
    ...(sells ? [{ id: "sell", label: t("shop.tab.sell") }] : []),
    ...(manages ? [{ id: "products", label: t("shop.tab.products") }] : []),
    ...(money ? [{ id: "sales", label: t("shop.tab.sales") }] : []),
  ];
  const tab = useTab(tabs.length ? tabs : [{ id: "none", label: "" }]);
  const [month, setMonth] = useState<string | undefined>(undefined);
  const products = useLoad(
    () => (sells || manages ? shopApi.products(manages) : Promise.resolve([])),
    [sells, manages],
  );
  const sales = useLoad(
    () => (money && tab === "sales" ? shopApi.sales(month) : Promise.resolve(null)),
    [money, tab, month],
  );
  useLive(["shop"], () => {
    products.reload();
    sales.reload();
  });

  if (!tabs.length)
    return <Notice tone="error">{t("errors.permission_denied")}</Notice>;
  const error = products.error || sales.error;
  return (
    <div className="space-y-4">
      <PageHeader title={t("shop.title")} subtitle={t("shop.subtitle")} />
      {error && <Notice tone="error">{error}</Notice>}
      <Tabs tabs={tabs} label={t("shop.title")}>
        {!products.data ? (
          <PageSkeleton label={t("common.loading")} />
        ) : tab === "sell" ? (
          <Till
            products={products.data.filter((p) => p.is_active)}
            onSold={products.reload}
          />
        ) : tab === "products" ? (
          <Products products={products.data} onChanged={products.reload} />
        ) : sales.data ? (
          <SalesList data={sales.data} onMonth={setMonth} onChanged={sales.reload} />
        ) : (
          <PageSkeleton label={t("common.loading")} />
        )}
      </Tabs>
    </div>
  );
}
