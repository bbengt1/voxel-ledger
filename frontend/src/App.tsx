import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { HomePage } from "@/pages/Home";
import { LoginPage } from "@/pages/Login";
import { CustomFieldsPage } from "@/pages/admin/CustomFields";
import { UserCreatePage } from "@/pages/admin/UserCreate";
import { UserDetailPage } from "@/pages/admin/UserDetail";
import { UsersListPage } from "@/pages/admin/UsersList";
import { MaterialCreatePage } from "@/pages/catalog/MaterialCreate";
import { MaterialDetailPage } from "@/pages/catalog/MaterialDetail";
import { MaterialsListPage } from "@/pages/catalog/MaterialsList";
import { ProductCreatePage } from "@/pages/catalog/ProductCreate";
import { ProductDetailPage } from "@/pages/catalog/ProductDetail";
import { ProductsListPage } from "@/pages/catalog/ProductsList";
import { RateCreatePage } from "@/pages/catalog/RateCreate";
import { RateDetailPage } from "@/pages/catalog/RateDetail";
import { RatesListPage } from "@/pages/catalog/RatesList";
import { SuppliesListPage } from "@/pages/catalog/SuppliesList";
import { SupplyCreatePage } from "@/pages/catalog/SupplyCreate";
import { SupplyDetailPage } from "@/pages/catalog/SupplyDetail";
import { AccountsTreePage } from "@/pages/accounting/AccountsTree";
import { BudgetsListPage } from "@/pages/accounting/BudgetsList";
import { BudgetsVariancePage } from "@/pages/accounting/BudgetsVariance";
import { DivisionsListPage } from "@/pages/accounting/DivisionsList";
import { JournalEntriesListPage } from "@/pages/accounting/JournalEntriesList";
import { JournalEntryComposerPage } from "@/pages/accounting/JournalEntryComposer";
import { JournalEntryDetailPage } from "@/pages/accounting/JournalEntryDetail";
import { PeriodsListPage } from "@/pages/accounting/PeriodsList";
import { ApprovalDetailPage } from "@/pages/approvals/ApprovalDetail";
import { ApprovalsListPage } from "@/pages/approvals/ApprovalsList";
import { JobComposerPage } from "@/pages/production/JobComposer";
import { JobDetailPage } from "@/pages/production/JobDetail";
import { JobsListPage } from "@/pages/production/JobsList";
import { PrinterCreatePage } from "@/pages/production/PrinterCreate";
import { PrinterDetailPage } from "@/pages/production/PrinterDetail";
import { PrintersMonitorPage } from "@/pages/production/PrintersMonitor";
import { ProductionQueuePage } from "@/pages/production/ProductionQueue";
import { PosScreenPage } from "@/pages/sales/PosScreen";
import { RefundComposerPage } from "@/pages/sales/RefundComposer";
import { RefundDetailPage } from "@/pages/sales/RefundDetail";
import { LocationCreatePage } from "@/pages/inventory/LocationCreate";
import { LocationDetailPage } from "@/pages/inventory/LocationDetail";
import { AlertsListPage } from "@/pages/inventory/AlertsList";
import { LocationsListPage } from "@/pages/inventory/LocationsList";
import { StartingBalancesPage } from "@/pages/inventory/StartingBalances";
import { TransactionsListPage } from "@/pages/inventory/TransactionsList";
// --- 6.7a sales routes ---
import { ChannelsListPage } from "@/pages/sales/ChannelsList";
import { SaleComposerPage } from "@/pages/sales/SaleComposer";
import { SaleDetailPage } from "@/pages/sales/SaleDetail";
import { SalesListPage } from "@/pages/sales/SalesList";
import { ShipmentDetailPage } from "@/pages/sales/ShipmentDetail";
import { ShipmentNewPage } from "@/pages/sales/ShipmentNew";
// --- end 6.7a sales routes ---
// --- 7.8a AR routes ---
import { CustomerComposerPage } from "@/pages/ar/CustomerComposer";
import { CustomerDetailPage } from "@/pages/ar/CustomerDetail";
import { CustomersListPage } from "@/pages/ar/CustomersList";
import { InvoiceComposerPage } from "@/pages/ar/InvoiceComposer";
import { InvoiceDetailPage } from "@/pages/ar/InvoiceDetail";
import { InvoicesListPage } from "@/pages/ar/InvoicesList";
import { PaymentDetailPage } from "@/pages/ar/PaymentDetail";
import { PaymentsListPage } from "@/pages/ar/PaymentsList";
import { QuoteComposerPage } from "@/pages/ar/QuoteComposer";
import { QuoteDetailPage } from "@/pages/ar/QuoteDetail";
import { QuotesListPage } from "@/pages/ar/QuotesList";
import { RecordPaymentPage } from "@/pages/ar/RecordPayment";
// --- end 7.8a AR routes ---

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppShell>
              <HomePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/admin/users"
        element={
          <RequireAuth>
            <AppShell>
              <UsersListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/admin/users/new"
        element={
          <RequireAuth>
            <AppShell>
              <UserCreatePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/admin/users/:id"
        element={
          <RequireAuth>
            <AppShell>
              <UserDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/admin/custom-fields"
        element={
          <RequireAuth>
            <AppShell>
              <CustomFieldsPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/materials"
        element={
          <RequireAuth>
            <AppShell>
              <MaterialsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/materials/new"
        element={
          <RequireAuth>
            <AppShell>
              <MaterialCreatePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/materials/:id"
        element={
          <RequireAuth>
            <AppShell>
              <MaterialDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/products"
        element={
          <RequireAuth>
            <AppShell>
              <ProductsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/products/new"
        element={
          <RequireAuth>
            <AppShell>
              <ProductCreatePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/products/:id"
        element={
          <RequireAuth>
            <AppShell>
              <ProductDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/supplies"
        element={
          <RequireAuth>
            <AppShell>
              <SuppliesListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/supplies/new"
        element={
          <RequireAuth>
            <AppShell>
              <SupplyCreatePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/supplies/:id"
        element={
          <RequireAuth>
            <AppShell>
              <SupplyDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/inventory/locations"
        element={
          <RequireAuth>
            <AppShell>
              <LocationsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/inventory/locations/new"
        element={
          <RequireAuth>
            <AppShell>
              <LocationCreatePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/inventory/locations/:id"
        element={
          <RequireAuth>
            <AppShell>
              <LocationDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/inventory/transactions"
        element={
          <RequireAuth>
            <AppShell>
              <TransactionsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/inventory/alerts"
        element={
          <RequireAuth>
            <AppShell>
              <AlertsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/inventory/starting-balances"
        element={
          <RequireAuth>
            <AppShell>
              <StartingBalancesPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/rates"
        element={
          <RequireAuth>
            <AppShell>
              <RatesListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/rates/new"
        element={
          <RequireAuth>
            <AppShell>
              <RateCreatePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/catalog/rates/:id"
        element={
          <RequireAuth>
            <AppShell>
              <RateDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/accounting/accounts"
        element={
          <RequireAuth>
            <AppShell>
              <AccountsTreePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/accounting/entries"
        element={
          <RequireAuth>
            <AppShell>
              <JournalEntriesListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/accounting/entries/new"
        element={
          <RequireAuth>
            <AppShell>
              <JournalEntryComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/accounting/entries/:id"
        element={
          <RequireAuth>
            <AppShell>
              <JournalEntryDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/accounting/periods"
        element={
          <RequireAuth>
            <AppShell>
              <PeriodsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/accounting/divisions"
        element={
          <RequireAuth>
            <AppShell>
              <DivisionsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/accounting/budgets"
        element={
          <RequireAuth>
            <AppShell>
              <BudgetsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/accounting/budgets/variance"
        element={
          <RequireAuth>
            <AppShell>
              <BudgetsVariancePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/production/jobs"
        element={
          <RequireAuth>
            <AppShell>
              <JobsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/production/jobs/new"
        element={
          <RequireAuth>
            <AppShell>
              <JobComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/production/jobs/:id"
        element={
          <RequireAuth>
            <AppShell>
              <JobDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/production/queue"
        element={
          <RequireAuth>
            <AppShell>
              <ProductionQueuePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/production/printers"
        element={
          <RequireAuth>
            <AppShell>
              <PrintersMonitorPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/production/printers/new"
        element={
          <RequireAuth>
            <AppShell>
              <PrinterCreatePage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/production/printers/:id"
        element={
          <RequireAuth>
            <AppShell>
              <PrinterDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      {/* --- 6.7a + 6.7b sales routes --- */}
      {/* Specific paths first; dynamic /sales/:id last. */}
      <Route
        path="/sales"
        element={
          <RequireAuth>
            <AppShell>
              <SalesListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/sales/pos"
        element={
          <RequireAuth>
            <AppShell>
              <PosScreenPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/sales/channels"
        element={
          <RequireAuth>
            <AppShell>
              <ChannelsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/sales/new"
        element={
          <RequireAuth>
            <AppShell>
              <SaleComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/sales/refunds/:id"
        element={
          <RequireAuth>
            <AppShell>
              <RefundDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/sales/shipments/:id"
        element={
          <RequireAuth>
            <AppShell>
              <ShipmentDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/sales/:id/refund/new"
        element={
          <RequireAuth>
            <AppShell>
              <RefundComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/sales/:id/shipments/new"
        element={
          <RequireAuth>
            <AppShell>
              <ShipmentNewPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/sales/:id"
        element={
          <RequireAuth>
            <AppShell>
              <SaleDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      {/* --- end sales routes --- */}
      {/* --- 7.8a AR routes (specific first) --- */}
      <Route
        path="/customers"
        element={
          <RequireAuth>
            <AppShell>
              <CustomersListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/customers/new"
        element={
          <RequireAuth>
            <AppShell>
              <CustomerComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/customers/:id/edit"
        element={
          <RequireAuth>
            <AppShell>
              <CustomerComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/customers/:id"
        element={
          <RequireAuth>
            <AppShell>
              <CustomerDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/quotes"
        element={
          <RequireAuth>
            <AppShell>
              <QuotesListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/quotes/new"
        element={
          <RequireAuth>
            <AppShell>
              <QuoteComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/quotes/:id/edit"
        element={
          <RequireAuth>
            <AppShell>
              <QuoteComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/quotes/:id"
        element={
          <RequireAuth>
            <AppShell>
              <QuoteDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/invoices"
        element={
          <RequireAuth>
            <AppShell>
              <InvoicesListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/invoices/new"
        element={
          <RequireAuth>
            <AppShell>
              <InvoiceComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/invoices/:id/edit"
        element={
          <RequireAuth>
            <AppShell>
              <InvoiceComposerPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/invoices/:id"
        element={
          <RequireAuth>
            <AppShell>
              <InvoiceDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/payments"
        element={
          <RequireAuth>
            <AppShell>
              <PaymentsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/payments/new"
        element={
          <RequireAuth>
            <AppShell>
              <RecordPaymentPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/payments/:id"
        element={
          <RequireAuth>
            <AppShell>
              <PaymentDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      {/* --- end 7.8a AR routes --- */}
      <Route
        path="/approvals"
        element={
          <RequireAuth>
            <AppShell>
              <ApprovalsListPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/approvals/:id"
        element={
          <RequireAuth>
            <AppShell>
              <ApprovalDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
