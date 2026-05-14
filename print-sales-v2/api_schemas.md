# API Schemas (Components)

Auto-generated from OpenAPI (315 schemas).

## Index

- [`APAgingRow`](#schema-apagingrow)
- [`APAgingSummary`](#schema-apagingsummary)
- [`ARAgingReportResponse`](#schema-aragingreportresponse)
- [`ARAgingRow`](#schema-aragingrow)
- [`ARAgingSummary`](#schema-aragingsummary)
- [`AccountCreate`](#schema-accountcreate)
- [`AccountDrillDownResponse`](#schema-accountdrilldownresponse)
- [`AccountResponse`](#schema-accountresponse)
- [`AccountUpdate`](#schema-accountupdate)
- [`AccountingPeriodCreate`](#schema-accountingperiodcreate)
- [`AccountingPeriodResponse`](#schema-accountingperiodresponse)
- [`AccountingPeriodStatusUpdate`](#schema-accountingperiodstatusupdate)
- [`AccountingPeriodUpdate`](#schema-accountingperiodupdate)
- [`AddToInvoiceRequest`](#schema-addtoinvoicerequest)
- [`AmortizationPostRequest`](#schema-amortizationpostrequest)
- [`ApplyRequest`](#schema-applyrequest)
- [`ApplyWithholdingRequest`](#schema-applywithholdingrequest)
- [`ApprovalDecisionBody`](#schema-approvaldecisionbody)
- [`ApprovalRequestResponse`](#schema-approvalrequestresponse)
- [`ApproveRequest`](#schema-approverequest)
- [`AttachmentResponse`](#schema-attachmentresponse)
- [`AuditLogResponse`](#schema-auditlogresponse)
- [`BalanceSheetResponse`](#schema-balancesheetresponse)
- [`BalanceSheetSection`](#schema-balancesheetsection)
- [`BankAccountFlagRequest`](#schema-bankaccountflagrequest)
- [`BankAccountResponse`](#schema-bankaccountresponse)
- [`BatchRequest`](#schema-batchrequest)
- [`BillCreate`](#schema-billcreate)
- [`BillPaymentCreate`](#schema-billpaymentcreate)
- [`BillPaymentResponse`](#schema-billpaymentresponse)
- [`BillResponse`](#schema-billresponse)
- [`BillUpdate`](#schema-billupdate)
- [`BillableExpenseCreate`](#schema-billableexpensecreate)
- [`BillableExpenseResponse`](#schema-billableexpenseresponse)
- [`BillableExpenseUpdate`](#schema-billableexpenseupdate)
- [`Body_bulk_import_csv_api_v1_fixed_assets_bulk_import_csv_post`](#schema-body_bulk_import_csv_api_v1_fixed_assets_bulk_import_csv_post)
- [`Body_import_csv_api_v1_batch__scope__import_csv_post`](#schema-body_import_csv_api_v1_batch__scope__import_csv_post)
- [`Body_import_inventory_starting_balances_api_v1_inventory_starting_balances_inventory_csv_post`](#schema-body_import_inventory_starting_balances_api_v1_inventory_starting_balances_inventory_csv_post)
- [`Body_post_starting_balances_csv_api_v1_accounting_starting_balances_csv_post`](#schema-body_post_starting_balances_csv_api_v1_accounting_starting_balances_csv_post)
- [`Body_upload_api_v1_attachments__scope___record_id__post`](#schema-body_upload_api_v1_attachments__scope___record_id__post)
- [`Body_upload_import_api_v1_banking_imports_post`](#schema-body_upload_import_api_v1_banking_imports_post)
- [`BudgetResponse`](#schema-budgetresponse)
- [`BudgetUpsertRequest`](#schema-budgetupsertrequest)
- [`BudgetUpsertRow`](#schema-budgetupsertrow)
- [`BulkSettingUpdate`](#schema-bulksettingupdate)
- [`COGSBreakdownRow`](#schema-cogsbreakdownrow)
- [`COGSBreakdownSummary`](#schema-cogsbreakdownsummary)
- [`CalculateRequest`](#schema-calculaterequest)
- [`CalculateResponse`](#schema-calculateresponse)
- [`CameraCreate`](#schema-cameracreate)
- [`CameraResponse`](#schema-cameraresponse)
- [`CameraUpdate`](#schema-cameraupdate)
- [`CandidateResponse`](#schema-candidateresponse)
- [`CashFlowSection`](#schema-cashflowsection)
- [`CashFlowSummaryResponse`](#schema-cashflowsummaryresponse)
- [`ChannelBreakdown`](#schema-channelbreakdown)
- [`ClaimCreate`](#schema-claimcreate)
- [`ClaimResponse`](#schema-claimresponse)
- [`ConsumptionOut`](#schema-consumptionout)
- [`CreateFromLineBody`](#schema-createfromlinebody)
- [`CreateTxRequest`](#schema-createtxrequest)
- [`CreditNoteCreate`](#schema-creditnotecreate)
- [`CustomerCreate`](#schema-customercreate)
- [`CustomerCreditApply`](#schema-customercreditapply)
- [`CustomerCreditCreate`](#schema-customercreditcreate)
- [`CustomerCreditResponse`](#schema-customercreditresponse)
- [`CustomerResponse`](#schema-customerresponse)
- [`CustomerUpdate`](#schema-customerupdate)
- [`DNCreate`](#schema-dncreate)
- [`DNUpdate`](#schema-dnupdate)
- [`DashboardSummary`](#schema-dashboardsummary)
- [`DebitNoteCreate`](#schema-debitnotecreate)
- [`DefaultFulfillmentLocationResponse`](#schema-defaultfulfillmentlocationresponse)
- [`DefaultFulfillmentLocationUpdate`](#schema-defaultfulfillmentlocationupdate)
- [`DefinitionCreate`](#schema-definitioncreate)
- [`DefinitionResponse`](#schema-definitionresponse)
- [`DefinitionUpdate`](#schema-definitionupdate)
- [`DepreciationPostRequest`](#schema-depreciationpostrequest)
- [`DisposeRequest`](#schema-disposerequest)
- [`DivisionCreate`](#schema-divisioncreate)
- [`DivisionResponse`](#schema-divisionresponse)
- [`DivisionUpdate`](#schema-divisionupdate)
- [`DryRunResponse`](#schema-dryrunresponse)
- [`EmailDeliveryResponse`](#schema-emaildeliveryresponse)
- [`EmailSendRequest`](#schema-emailsendrequest)
- [`ExpenseCategoryCreate`](#schema-expensecategorycreate)
- [`ExpenseCategoryResponse`](#schema-expensecategoryresponse)
- [`ExpenseCategoryUpdate`](#schema-expensecategoryupdate)
- [`ExpenseSummaryRow`](#schema-expensesummaryrow)
- [`FifoFlagResponse`](#schema-fifoflagresponse)
- [`FifoFlagUpdate`](#schema-fifoflagupdate)
- [`FilamentResolveRequest`](#schema-filamentresolverequest)
- [`FinanceDashboardSummary`](#schema-financedashboardsummary)
- [`FixedAssetCreate`](#schema-fixedassetcreate)
- [`FixedAssetDetail`](#schema-fixedassetdetail)
- [`FixedAssetResponse`](#schema-fixedassetresponse)
- [`FixedAssetUpdate`](#schema-fixedassetupdate)
- [`HTTPValidationError`](#schema-httpvalidationerror)
- [`InsightEvidenceMetric`](#schema-insightevidencemetric)
- [`InsightItem`](#schema-insightitem)
- [`InsightRequest`](#schema-insightrequest)
- [`InsightStatusResponse`](#schema-insightstatusresponse)
- [`InsightSummaryResponse`](#schema-insightsummaryresponse)
- [`IntangibleAssetCreate`](#schema-intangibleassetcreate)
- [`IntangibleAssetDetail`](#schema-intangibleassetdetail)
- [`IntangibleAssetResponse`](#schema-intangibleassetresponse)
- [`IntangibleAssetUpdate`](#schema-intangibleassetupdate)
- [`InventoryAlert`](#schema-inventoryalert)
- [`InventoryReconcileRequest`](#schema-inventoryreconcilerequest)
- [`InventoryReconcileResponse`](#schema-inventoryreconcileresponse)
- [`InventoryReportResponse`](#schema-inventoryreportresponse)
- [`InventoryTransactionCreate`](#schema-inventorytransactioncreate)
- [`InventoryTransactionResponse`](#schema-inventorytransactionresponse)
- [`InventoryValuationRow`](#schema-inventoryvaluationrow)
- [`InventoryValuationSummary`](#schema-inventoryvaluationsummary)
- [`InvoiceCreate`](#schema-invoicecreate)
- [`InvoiceFromQuoteCreate`](#schema-invoicefromquotecreate)
- [`InvoiceLineCreate`](#schema-invoicelinecreate)
- [`InvoiceLineResponse`](#schema-invoicelineresponse)
- [`InvoicePaymentApply`](#schema-invoicepaymentapply)
- [`InvoiceResponse`](#schema-invoiceresponse)
- [`InvoiceStatus`](#schema-invoicestatus)
- [`InvoiceUpdate`](#schema-invoiceupdate)
- [`JobCreate`](#schema-jobcreate)
- [`JobResponse`](#schema-jobresponse)
- [`JobStatus`](#schema-jobstatus)
- [`JobUpdate`](#schema-jobupdate)
- [`JournalEntryCreate`](#schema-journalentrycreate)
- [`JournalEntryResponse`](#schema-journalentryresponse)
- [`JournalEntryReverse`](#schema-journalentryreverse)
- [`JournalLineCreate`](#schema-journallinecreate)
- [`JournalLineDTO`](#schema-journallinedto)
- [`JournalLineDrillRow`](#schema-journallinedrillrow)
- [`JournalLineResponse`](#schema-journallineresponse)
- [`JournalLineSuggestion`](#schema-journallinesuggestion)
- [`KitComponentResponse`](#schema-kitcomponentresponse)
- [`KitComponentRow`](#schema-kitcomponentrow)
- [`KitDefinitionRequest`](#schema-kitdefinitionrequest)
- [`KitResponse`](#schema-kitresponse)
- [`LineOut`](#schema-lineout)
- [`LocationCreate`](#schema-locationcreate)
- [`LocationResponse`](#schema-locationresponse)
- [`LocationStockRow`](#schema-locationstockrow)
- [`LocationUpdate`](#schema-locationupdate)
- [`LoginRequest`](#schema-loginrequest)
- [`MappingResponse`](#schema-mappingresponse)
- [`MappingUpsertRequest`](#schema-mappingupsertrequest)
- [`MarketplaceSettlementCreate`](#schema-marketplacesettlementcreate)
- [`MarketplaceSettlementResponse`](#schema-marketplacesettlementresponse)
- [`MatchRequest`](#schema-matchrequest)
- [`MaterialCreate`](#schema-materialcreate)
- [`MaterialReceiptCreate`](#schema-materialreceiptcreate)
- [`MaterialReceiptResponse`](#schema-materialreceiptresponse)
- [`MaterialResponse`](#schema-materialresponse)
- [`MaterialUpdate`](#schema-materialupdate)
- [`MaterialUsageDataPoint`](#schema-materialusagedatapoint)
- [`MergeRequest`](#schema-mergerequest)
- [`PLReportResponse`](#schema-plreportresponse)
- [`PLRow`](#schema-plrow)
- [`PLSummary`](#schema-plsummary)
- [`PODetail`](#schema-podetail)
- [`POResponse`](#schema-poresponse)
- [`POSCheckoutCreate`](#schema-poscheckoutcreate)
- [`POSProductScanRequest`](#schema-posproductscanrequest)
- [`PaginatedCameras`](#schema-paginatedcameras)
- [`PaginatedInvoices`](#schema-paginatedinvoices)
- [`PaginatedJobs`](#schema-paginatedjobs)
- [`PaginatedPrinters`](#schema-paginatedprinters)
- [`PaginatedProducts`](#schema-paginatedproducts)
- [`PaginatedQuotes`](#schema-paginatedquotes)
- [`PaginatedSales`](#schema-paginatedsales)
- [`PaginatedTransactions`](#schema-paginatedtransactions)
- [`PasswordChange`](#schema-passwordchange)
- [`PaymentCreate`](#schema-paymentcreate)
- [`PaymentMethodBreakdown`](#schema-paymentmethodbreakdown)
- [`PaymentResponse`](#schema-paymentresponse)
- [`PeriodCloseDateResponse`](#schema-periodclosedateresponse)
- [`PeriodCloseDateUpdate`](#schema-periodclosedateupdate)
- [`PlateIn`](#schema-platein)
- [`PlateResponse`](#schema-plateresponse)
- [`PreventNegativeStockResponse`](#schema-preventnegativestockresponse)
- [`PreventNegativeStockUpdate`](#schema-preventnegativestockupdate)
- [`PrinterConnectionTestResponse`](#schema-printerconnectiontestresponse)
- [`PrinterCreate`](#schema-printercreate)
- [`PrinterHistoryEventResponse`](#schema-printerhistoryeventresponse)
- [`PrinterMonitorProvider`](#schema-printermonitorprovider)
- [`PrinterResponse`](#schema-printerresponse)
- [`PrinterStatus`](#schema-printerstatus)
- [`PrinterThumbnailResponse`](#schema-printerthumbnailresponse)
- [`PrinterUpdate`](#schema-printerupdate)
- [`ProductBOMAvailability`](#schema-productbomavailability)
- [`ProductBOMItemCreate`](#schema-productbomitemcreate)
- [`ProductBOMItemResponse`](#schema-productbomitemresponse)
- [`ProductBOMReplace`](#schema-productbomreplace)
- [`ProductBOMSummary`](#schema-productbomsummary)
- [`ProductBarcodeGenerateResponse`](#schema-productbarcodegenerateresponse)
- [`ProductCreate`](#schema-productcreate)
- [`ProductRanking`](#schema-productranking)
- [`ProductResponse`](#schema-productresponse)
- [`ProductUpdate`](#schema-productupdate)
- [`ProfileCreate`](#schema-profilecreate)
- [`ProfileResponse`](#schema-profileresponse)
- [`ProfileUpdate`](#schema-profileupdate)
- [`ProfitAndLossComparisonResponse`](#schema-profitandlosscomparisonresponse)
- [`ProfitAndLossResponse`](#schema-profitandlossresponse)
- [`ProfitAndLossSection`](#schema-profitandlosssection)
- [`ProfitMarginDataPoint`](#schema-profitmargindatapoint)
- [`ProjectCreate`](#schema-projectcreate)
- [`ProjectResponse`](#schema-projectresponse)
- [`ProjectUpdate`](#schema-projectupdate)
- [`PromoteRequest`](#schema-promoterequest)
- [`QuoteConvertToJob`](#schema-quoteconverttojob)
- [`QuoteCreate`](#schema-quotecreate)
- [`QuoteResponse`](#schema-quoteresponse)
- [`QuoteStatus`](#schema-quotestatus)
- [`QuoteUpdate`](#schema-quoteupdate)
- [`RJECreate`](#schema-rjecreate)
- [`RJEResponse`](#schema-rjeresponse)
- [`RJEUpdate`](#schema-rjeupdate)
- [`RateCreate`](#schema-ratecreate)
- [`RateResponse`](#schema-rateresponse)
- [`RateUpdate`](#schema-rateupdate)
- [`ReconciliationCreateRequest`](#schema-reconciliationcreaterequest)
- [`ReconciliationDetailResponse`](#schema-reconciliationdetailresponse)
- [`ReconciliationLineToggle`](#schema-reconciliationlinetoggle)
- [`RecurringExpenseCreate`](#schema-recurringexpensecreate)
- [`RecurringExpenseGenerate`](#schema-recurringexpensegenerate)
- [`RecurringExpenseResponse`](#schema-recurringexpenseresponse)
- [`RecurringExpenseUpdate`](#schema-recurringexpenseupdate)
- [`RecurringInvoiceCreate`](#schema-recurringinvoicecreate)
- [`RecurringInvoiceResponse`](#schema-recurringinvoiceresponse)
- [`RecurringInvoiceUpdate`](#schema-recurringinvoiceupdate)
- [`RefundInCashRequest`](#schema-refundincashrequest)
- [`RefundRequestBody`](#schema-refundrequestbody)
- [`ReimburseAsBillRequest`](#schema-reimburseasbillrequest)
- [`ReimburseRequest`](#schema-reimburserequest)
- [`RejectRequest`](#schema-rejectrequest)
- [`RevenueDataPoint`](#schema-revenuedatapoint)
- [`RuleCreate`](#schema-rulecreate)
- [`RuleResponse`](#schema-ruleresponse)
- [`RuleUpdate`](#schema-ruleupdate)
- [`SOCreate`](#schema-socreate)
- [`SaleCreate`](#schema-salecreate)
- [`SaleItemCreate`](#schema-saleitemcreate)
- [`SaleItemResponse`](#schema-saleitemresponse)
- [`SaleListResponse`](#schema-salelistresponse)
- [`SaleResponse`](#schema-saleresponse)
- [`SaleStatus`](#schema-salestatus)
- [`SaleUpdate`](#schema-saleupdate)
- [`SalesChannelCreate`](#schema-saleschannelcreate)
- [`SalesChannelResponse`](#schema-saleschannelresponse)
- [`SalesChannelUpdate`](#schema-saleschannelupdate)
- [`SalesMetrics`](#schema-salesmetrics)
- [`SalesReportResponse`](#schema-salesreportresponse)
- [`SalesReportRow`](#schema-salesreportrow)
- [`ScheduleRow`](#schema-schedulerow)
- [`SettingResponse`](#schema-settingresponse)
- [`SettingUpdate`](#schema-settingupdate)
- [`SettlementLineCreate`](#schema-settlementlinecreate)
- [`SettlementLineResponse`](#schema-settlementlineresponse)
- [`SettlementReconciliationRow`](#schema-settlementreconciliationrow)
- [`SettlementReconciliationSummary`](#schema-settlementreconciliationsummary)
- [`SourceCreate`](#schema-sourcecreate)
- [`SourceResponse`](#schema-sourceresponse)
- [`SourceUpdate`](#schema-sourceupdate)
- [`StartingBalanceLine`](#schema-startingbalanceline)
- [`StartingBalancesRequest`](#schema-startingbalancesrequest)
- [`StatementImportResponse`](#schema-statementimportresponse)
- [`StatementLine`](#schema-statementline)
- [`StatementLineResponse`](#schema-statementlineresponse)
- [`StockLevelRow`](#schema-stocklevelrow)
- [`SupplyAdjust`](#schema-supplyadjust)
- [`SupplyCreate`](#schema-supplycreate)
- [`SupplyResponse`](#schema-supplyresponse)
- [`SupplyUpdate`](#schema-supplyupdate)
- [`SuspenseReclassifyRequest`](#schema-suspensereclassifyrequest)
- [`TaxLiabilityReportResponse`](#schema-taxliabilityreportresponse)
- [`TaxLiabilityRow`](#schema-taxliabilityrow)
- [`TaxLiabilitySummary`](#schema-taxliabilitysummary)
- [`TaxProfileCreate`](#schema-taxprofilecreate)
- [`TaxProfileResponse`](#schema-taxprofileresponse)
- [`TaxProfileUpdate`](#schema-taxprofileupdate)
- [`TaxRemittanceCreate`](#schema-taxremittancecreate)
- [`TaxRemittanceResponse`](#schema-taxremittanceresponse)
- [`TemplateCreate`](#schema-templatecreate)
- [`TemplateResponse`](#schema-templateresponse)
- [`TemplateUpdate`](#schema-templateupdate)
- [`TokenResponse`](#schema-tokenresponse)
- [`TransactionType`](#schema-transactiontype)
- [`TransferEdit`](#schema-transferedit)
- [`TransferLineIn`](#schema-transferlinein)
- [`TransferLineOut`](#schema-transferlineout)
- [`UserCreate`](#schema-usercreate)
- [`UserResponse`](#schema-userresponse)
- [`UserRole`](#schema-userrole)
- [`UserUpdate`](#schema-userupdate)
- [`ValidationError`](#schema-validationerror)
- [`ValueUpsert`](#schema-valueupsert)
- [`VendorCreate`](#schema-vendorcreate)
- [`VendorResponse`](#schema-vendorresponse)
- [`VendorUpdate`](#schema-vendorupdate)
- [`app__api__v1__endpoints__accounting_foundations__RunResponse`](#schema-app__api__v1__endpoints__accounting_foundations__runresponse)
- [`app__api__v1__endpoints__accounting_foundations__TemplateLine`](#schema-app__api__v1__endpoints__accounting_foundations__templateline)
- [`app__api__v1__endpoints__delivery_notes__LineIn`](#schema-app__api__v1__endpoints__delivery_notes__linein)
- [`app__api__v1__endpoints__expense_claims__LineIn`](#schema-app__api__v1__endpoints__expense_claims__linein)
- [`app__api__v1__endpoints__inter_account_transfers__TransferCreate`](#schema-app__api__v1__endpoints__inter_account_transfers__transfercreate)
- [`app__api__v1__endpoints__inter_account_transfers__TransferResponse`](#schema-app__api__v1__endpoints__inter_account_transfers__transferresponse)
- [`app__api__v1__endpoints__locations__TransferCreate`](#schema-app__api__v1__endpoints__locations__transfercreate)
- [`app__api__v1__endpoints__locations__TransferResponse`](#schema-app__api__v1__endpoints__locations__transferresponse)
- [`app__api__v1__endpoints__notes__LineIn`](#schema-app__api__v1__endpoints__notes__linein)
- [`app__api__v1__endpoints__orders__LineIn`](#schema-app__api__v1__endpoints__orders__linein)
- [`app__api__v1__endpoints__orders__POCreate`](#schema-app__api__v1__endpoints__orders__pocreate)
- [`app__api__v1__endpoints__production_orders__POCreate`](#schema-app__api__v1__endpoints__production_orders__pocreate)
- [`app__api__v1__endpoints__recurring_invoices__RunResponse`](#schema-app__api__v1__endpoints__recurring_invoices__runresponse)
- [`app__api__v1__endpoints__recurring_invoices__TemplateLine`](#schema-app__api__v1__endpoints__recurring_invoices__templateline)

---

### `APAgingRow` <a id="schema-apagingrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `bill_id` | string | ✓ |  |
| `bill_number` | string \| null |  |  |
| `vendor_name` | string \| null |  |  |
| `due_date` | string(date) \| null |  |  |
| `balance_due` | string | ✓ |  |
| `current` | string | ✓ |  |
| `bucket_1_30` | string | ✓ |  |
| `bucket_31_60` | string | ✓ |  |
| `bucket_61_90` | string | ✓ |  |
| `bucket_90_plus` | string | ✓ |  |

---

### `APAgingSummary` <a id="schema-apagingsummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `as_of_date` | string(date) | ✓ |  |
| `rows` | [`APAgingRow`](#schema-apagingrow)[] | ✓ |  |
| `current_total` | string | ✓ |  |
| `bucket_1_30_total` | string | ✓ |  |
| `bucket_31_60_total` | string | ✓ |  |
| `bucket_61_90_total` | string | ✓ |  |
| `bucket_90_plus_total` | string | ✓ |  |
| `total_outstanding` | string | ✓ |  |

---

### `ARAgingReportResponse` <a id="schema-aragingreportresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `as_of_date` | string(date) | ✓ |  |
| `rows` | [`ARAgingRow`](#schema-aragingrow)[] | ✓ |  |
| `current_total` | string | ✓ |  |
| `bucket_1_30_total` | string | ✓ |  |
| `bucket_31_60_total` | string | ✓ |  |
| `bucket_61_90_total` | string | ✓ |  |
| `bucket_90_plus_total` | string | ✓ |  |
| `total_outstanding` | string | ✓ |  |

---

### `ARAgingRow` <a id="schema-aragingrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `invoice_id` | string(uuid) | ✓ |  |
| `invoice_number` | string | ✓ |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `due_date` | string(date) \| null |  |  |
| `balance_due` | string | ✓ |  |
| `current` | string | ✓ |  |
| `bucket_1_30` | string | ✓ |  |
| `bucket_31_60` | string | ✓ |  |
| `bucket_61_90` | string | ✓ |  |
| `bucket_90_plus` | string | ✓ |  |

---

### `ARAgingSummary` <a id="schema-aragingsummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `as_of_date` | string(date) | ✓ |  |
| `rows` | [`ARAgingRow`](#schema-aragingrow)[] | ✓ |  |
| `current_total` | string | ✓ |  |
| `bucket_1_30_total` | string | ✓ |  |
| `bucket_31_60_total` | string | ✓ |  |
| `bucket_61_90_total` | string | ✓ |  |
| `bucket_90_plus_total` | string | ✓ |  |
| `total_outstanding` | string | ✓ |  |

---

### `AccountCreate` <a id="schema-accountcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `code` | string | ✓ | max 20 |
| `name` | string | ✓ | max 120 |
| `account_type` | string | ✓ |  |
| `normal_balance` | string | ✓ |  |
| `parent_id` | string(uuid) \| null |  |  |
| `description` | string \| null |  |  |
| `is_active` | boolean |  | default `True` |

---

### `AccountDrillDownResponse` <a id="schema-accountdrilldownresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `account_id` | string | ✓ |  |
| `account_code` | string | ✓ |  |
| `account_name` | string | ✓ |  |
| `date_from` | string \| null |  |  |
| `date_to` | string \| null |  |  |
| `rows` | [`JournalLineDrillRow`](#schema-journallinedrillrow)[] | ✓ |  |
| `total_debit` | string | ✓ |  |
| `total_credit` | string | ✓ |  |
| `net_change` | string | ✓ |  |

---

### `AccountResponse` <a id="schema-accountresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `code` | string | ✓ |  |
| `name` | string | ✓ |  |
| `account_type` | string | ✓ |  |
| `normal_balance` | string | ✓ |  |
| `parent_id` | string(uuid) \| null |  |  |
| `description` | string \| null |  |  |
| `is_active` | boolean | ✓ |  |
| `is_system` | boolean | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `AccountUpdate` <a id="schema-accountupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `account_type` | string \| null |  |  |
| `normal_balance` | string \| null |  |  |
| `parent_id` | string(uuid) \| null |  |  |
| `description` | string \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `AccountingPeriodCreate` <a id="schema-accountingperiodcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `period_key` | string | ✓ | max 20 |
| `name` | string | ✓ | max 100 |
| `start_date` | string(date) | ✓ |  |
| `end_date` | string(date) | ✓ |  |
| `status` | string |  | default `'open'` |
| `is_adjustment_period` | boolean |  | default `False` |

---

### `AccountingPeriodResponse` <a id="schema-accountingperiodresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `period_key` | string | ✓ |  |
| `name` | string | ✓ |  |
| `start_date` | string(date) | ✓ |  |
| `end_date` | string(date) | ✓ |  |
| `status` | string | ✓ |  |
| `is_adjustment_period` | boolean | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `AccountingPeriodStatusUpdate` <a id="schema-accountingperiodstatusupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `status` | string | ✓ |  |

---

### `AccountingPeriodUpdate` <a id="schema-accountingperiodupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `start_date` | string(date) \| null |  |  |
| `end_date` | string(date) \| null |  |  |
| `status` | string \| null |  |  |
| `is_adjustment_period` | boolean \| null |  |  |

---

### `AddToInvoiceRequest` <a id="schema-addtoinvoicerequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `invoice_id` | string(uuid) | ✓ |  |

---

### `AmortizationPostRequest` <a id="schema-amortizationpostrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `period_end` | string(date) | ✓ |  |
| `asset_ids` | string(uuid)[] \| null |  |  |

---

### `ApplyRequest` <a id="schema-applyrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `target_id` | string(uuid) | ✓ |  |
| `amount` | number \| string | ✓ |  |
| `applied_on` | string(date) \| null |  |  |

---

### `ApplyWithholdingRequest` <a id="schema-applywithholdingrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `gross_amount` | number \| string | ✓ |  |
| `cash_account_id` | string(uuid) | ✓ |  |
| `paid_on` | string(date) \| null |  |  |

---

### `ApprovalDecisionBody` <a id="schema-approvaldecisionbody"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `decision_notes` | string \| null |  |  |

---

### `ApprovalRequestResponse` <a id="schema-approvalrequestresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `action_type` | string | ✓ |  |
| `entity_type` | string | ✓ |  |
| `entity_id` | string \| null |  |  |
| `requested_by_user_id` | string(uuid) | ✓ |  |
| `approved_by_user_id` | string(uuid) \| null |  |  |
| `status` | string | ✓ |  |
| `reason` | string | ✓ |  |
| `request_payload` | object | ✓ |  |
| `decision_notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |
| `decided_at` | string(date-time) \| null |  |  |

---

### `ApproveRequest` <a id="schema-approverequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `approve_date` | string(date) \| null |  |  |

---

### `AttachmentResponse` <a id="schema-attachmentresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `scope` | string | ✓ |  |
| `record_id` | string(uuid) | ✓ |  |
| `filename` | string | ✓ |  |
| `content_type` | string | ✓ |  |
| `size_bytes` | integer | ✓ |  |
| `description` | string \| null | ✓ |  |
| `has_thumbnail` | boolean | ✓ |  |
| `sha256` | string | ✓ |  |
| `uploaded_at` | string(date-time) | ✓ |  |

---

### `AuditLogResponse` <a id="schema-auditlogresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `actor_user_id` | string(uuid) \| null |  |  |
| `entity_type` | string | ✓ |  |
| `entity_id` | string | ✓ |  |
| `action` | string | ✓ |  |
| `reason` | string \| null |  |  |
| `before_snapshot` | object \| null |  |  |
| `after_snapshot` | object \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `BalanceSheetResponse` <a id="schema-balancesheetresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `as_of_date` | string | ✓ |  |
| `assets` | [`BalanceSheetSection`](#schema-balancesheetsection) | ✓ |  |
| `liabilities` | [`BalanceSheetSection`](#schema-balancesheetsection) | ✓ |  |
| `equity` | [`BalanceSheetSection`](#schema-balancesheetsection) | ✓ |  |
| `liabilities_and_equity_total` | string | ✓ |  |
| `is_balanced` | boolean | ✓ |  |

---

### `BalanceSheetSection` <a id="schema-balancesheetsection"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `lines` | [`StatementLine`](#schema-statementline)[] | ✓ |  |
| `total` | string | ✓ |  |

---

### `BankAccountFlagRequest` <a id="schema-bankaccountflagrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `is_bank_account` | boolean | ✓ |  |
| `bank_account_kind` | enum("checking", "savings", "credit_card", "payment_processor") \| null |  |  |

---

### `BankAccountResponse` <a id="schema-bankaccountresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `code` | string | ✓ |  |
| `name` | string | ✓ |  |
| `account_type` | string | ✓ |  |
| `is_bank_account` | boolean | ✓ |  |
| `bank_account_kind` | string \| null | ✓ |  |
| `running_balance` | string | ✓ |  |

---

### `BatchRequest` <a id="schema-batchrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `ids` | string(uuid)[] | ✓ |  |

---

### `BillCreate` <a id="schema-billcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `vendor_id` | string(uuid) \| null |  |  |
| `expense_category_id` | string(uuid) \| null |  |  |
| `account_id` | string(uuid) | ✓ |  |
| `bill_number` | string \| null |  |  |
| `description` | string | ✓ | max 255 |
| `issue_date` | string(date) | ✓ |  |
| `due_date` | string(date) \| null |  |  |
| `amount` | number \| string | ✓ |  |
| `tax_amount` | number \| string |  | default `0` |
| `payment_method` | string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `BillPaymentCreate` <a id="schema-billpaymentcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `payment_date` | string(date) | ✓ |  |
| `amount` | number \| string | ✓ |  |
| `payment_method` | string \| null |  |  |
| `reference_number` | string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `BillPaymentResponse` <a id="schema-billpaymentresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `bill_id` | string(uuid) | ✓ |  |
| `payment_date` | string(date) | ✓ |  |
| `amount` | string | ✓ |  |
| `payment_method` | string \| null |  |  |
| `reference_number` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `BillResponse` <a id="schema-billresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `vendor_id` | string(uuid) \| null |  |  |
| `expense_category_id` | string(uuid) \| null |  |  |
| `account_id` | string(uuid) | ✓ |  |
| `bill_number` | string \| null |  |  |
| `description` | string | ✓ |  |
| `issue_date` | string(date) | ✓ |  |
| `due_date` | string(date) \| null |  |  |
| `amount` | string | ✓ |  |
| `tax_amount` | string | ✓ |  |
| `amount_paid` | string | ✓ |  |
| `status` | string | ✓ |  |
| `payment_method` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |
| `updated_at` | string(date-time) | ✓ |  |
| `payments` | [`BillPaymentResponse`](#schema-billpaymentresponse)[] |  | default `[]` |

---

### `BillUpdate` <a id="schema-billupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `vendor_id` | string(uuid) \| null |  |  |
| `expense_category_id` | string(uuid) \| null |  |  |
| `account_id` | string(uuid) \| null |  |  |
| `bill_number` | string \| null |  |  |
| `description` | string \| null |  |  |
| `issue_date` | string(date) \| null |  |  |
| `due_date` | string(date) \| null |  |  |
| `amount` | number \| string \| null |  |  |
| `tax_amount` | number \| string \| null |  |  |
| `payment_method` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `status` | string \| null |  |  |

---

### `BillableExpenseCreate` <a id="schema-billableexpensecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `customer_id` | string(uuid) | ✓ |  |
| `bill_id` | string(uuid) \| null |  |  |
| `description` | string | ✓ | max 255 |
| `cost` | number \| string | ✓ |  |
| `markup_pct` | number \| string |  | default `0` |
| `incurred_on` | string(date) | ✓ |  |
| `notes` | string \| null |  |  |

---

### `BillableExpenseResponse` <a id="schema-billableexpenseresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `customer_id` | string(uuid) | ✓ |  |
| `bill_id` | string(uuid) \| null | ✓ |  |
| `description` | string | ✓ |  |
| `cost` | string | ✓ |  |
| `markup_pct` | string | ✓ |  |
| `incurred_on` | string(date) | ✓ |  |
| `status` | string | ✓ |  |
| `invoice_id` | string(uuid) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `rebillable_amount` | string | ✓ |  |

---

### `BillableExpenseUpdate` <a id="schema-billableexpenseupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `description` | string \| null |  |  |
| `cost` | number \| string \| null |  |  |
| `markup_pct` | number \| string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `Body_bulk_import_csv_api_v1_fixed_assets_bulk_import_csv_post` <a id="schema-body_bulk_import_csv_api_v1_fixed_assets_bulk_import_csv_post"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `file` | string(binary) | ✓ |  |

---

### `Body_import_csv_api_v1_batch__scope__import_csv_post` <a id="schema-body_import_csv_api_v1_batch__scope__import_csv_post"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `file` | string(binary) | ✓ |  |

---

### `Body_import_inventory_starting_balances_api_v1_inventory_starting_balances_inventory_csv_post` <a id="schema-body_import_inventory_starting_balances_api_v1_inventory_starting_balances_inventory_csv_post"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `file` | string(binary) | ✓ |  |

---

### `Body_post_starting_balances_csv_api_v1_accounting_starting_balances_csv_post` <a id="schema-body_post_starting_balances_csv_api_v1_accounting_starting_balances_csv_post"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `file` | string(binary) | ✓ |  |

---

### `Body_upload_api_v1_attachments__scope___record_id__post` <a id="schema-body_upload_api_v1_attachments__scope___record_id__post"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `file` | string(binary) | ✓ |  |
| `description` | string \| null |  |  |

---

### `Body_upload_import_api_v1_banking_imports_post` <a id="schema-body_upload_import_api_v1_banking_imports_post"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `account_id` | string(uuid) | ✓ |  |
| `source_format` | enum("ofx", "qfx", "csv") |  | default `'ofx'` |
| `file` | string(binary) | ✓ |  |

---

### `BudgetResponse` <a id="schema-budgetresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `account_id` | string(uuid) | ✓ |  |
| `year` | integer | ✓ |  |
| `month` | integer | ✓ |  |
| `amount` | string | ✓ |  |

---

### `BudgetUpsertRequest` <a id="schema-budgetupsertrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `rows` | [`BudgetUpsertRow`](#schema-budgetupsertrow)[] | ✓ |  |

---

### `BudgetUpsertRow` <a id="schema-budgetupsertrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `account_id` | string(uuid) | ✓ |  |
| `year` | integer | ✓ | ≥ 2000.0; ≤ 2100.0 |
| `month` | integer | ✓ | ≥ 1.0; ≤ 12.0 |
| `amount` | number \| string | ✓ |  |

---

### `BulkSettingUpdate` <a id="schema-bulksettingupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `settings` | object<string, string> | ✓ |  |

---

### `COGSBreakdownRow` <a id="schema-cogsbreakdownrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `period` | string | ✓ |  |
| `channel_name` | string | ✓ |  |
| `product_description` | string | ✓ |  |
| `units_sold` | integer | ✓ |  |
| `cogs` | string | ✓ |  |
| `revenue` | string | ✓ |  |

---

### `COGSBreakdownSummary` <a id="schema-cogsbreakdownsummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `rows` | [`COGSBreakdownRow`](#schema-cogsbreakdownrow)[] | ✓ |  |
| `total_units_sold` | integer | ✓ |  |
| `total_cogs` | string | ✓ |  |
| `total_revenue` | string | ✓ |  |

---

### `CalculateRequest` <a id="schema-calculaterequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `qty_per_plate` | integer | ✓ |  |
| `num_plates` | integer | ✓ |  |
| `material_id` | string(uuid) | ✓ |  |
| `material_per_plate_g` | number \| string | ✓ |  |
| `print_time_per_plate_hrs` | number \| string | ✓ |  |
| `labor_mins` | number \| string |  | default `'0'` |
| `design_time_hrs` | number \| string \| null |  | default `'0'` |
| `shipping_cost` | number \| string |  | default `'0'` |
| `target_margin_pct` | number \| string |  | default `'40'` |

---

### `CalculateResponse` <a id="schema-calculateresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `total_pieces` | integer | ✓ |  |
| `electricity_cost` | number | ✓ |  |
| `material_cost` | number | ✓ |  |
| `labor_cost` | number | ✓ |  |
| `design_cost` | number | ✓ |  |
| `machine_cost` | number | ✓ |  |
| `packaging_cost` | number | ✓ |  |
| `shipping_cost` | number | ✓ |  |
| `failure_buffer` | number | ✓ |  |
| `subtotal_cost` | number | ✓ |  |
| `overhead` | number | ✓ |  |
| `total_cost` | number | ✓ |  |
| `cost_per_piece` | number | ✓ |  |
| `price_per_piece` | number | ✓ |  |
| `total_revenue` | number | ✓ |  |
| `platform_fees` | number | ✓ |  |
| `net_profit` | number | ✓ |  |
| `profit_per_piece` | number | ✓ |  |

---

### `CameraCreate` <a id="schema-cameracreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `slug` | string | ✓ | max 120 |
| `go2rtc_base_url` | string | ✓ | max 500 |
| `stream_name` | string | ✓ | max 120 |
| `printer_id` | string(uuid) \| null |  |  |
| `is_active` | boolean |  | default `True` |
| `notes` | string \| null |  |  |

---

### `CameraResponse` <a id="schema-cameraresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `slug` | string | ✓ |  |
| `go2rtc_base_url` | string | ✓ |  |
| `stream_name` | string | ✓ |  |
| `printer_id` | string(uuid) \| null |  |  |
| `printer_name` | string \| null |  |  |
| `is_active` | boolean | ✓ |  |
| `notes` | string \| null |  |  |
| `snapshot_url` | string \| null |  |  |
| `mse_ws_url` | string \| null |  |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `CameraUpdate` <a id="schema-cameraupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `slug` | string \| null |  |  |
| `go2rtc_base_url` | string \| null |  |  |
| `stream_name` | string \| null |  |  |
| `printer_id` | string(uuid) \| null |  |  |
| `clear_printer_id` | boolean |  | default `False` |
| `is_active` | boolean \| null |  |  |
| `notes` | string \| null |  |  |

---

### `CandidateResponse` <a id="schema-candidateresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `source_id` | string(uuid) | ✓ |  |
| `fingerprint` | string | ✓ |  |
| `discovered_at` | string(date-time) | ✓ |  |
| `source_filename` | string | ✓ |  |
| `source_path` | string \| null | ✓ |  |
| `file_size_bytes` | integer \| null | ✓ |  |
| `detected_metadata` | object \| null | ✓ |  |
| `status` | string | ✓ |  |
| `promoted_job_id` | string(uuid) \| null | ✓ |  |
| `parse_warnings` | string \| null | ✓ |  |

---

### `CashFlowSection` <a id="schema-cashflowsection"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `total` | string | ✓ |  |

---

### `CashFlowSummaryResponse` <a id="schema-cashflowsummaryresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `date_from` | string \| null |  |  |
| `date_to` | string \| null |  |  |
| `operating` | [`CashFlowSection`](#schema-cashflowsection) | ✓ |  |
| `investing` | [`CashFlowSection`](#schema-cashflowsection) | ✓ |  |
| `financing` | [`CashFlowSection`](#schema-cashflowsection) | ✓ |  |
| `net_change_in_cash` | string | ✓ |  |

---

### `ChannelBreakdown` <a id="schema-channelbreakdown"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `channel_name` | string | ✓ |  |
| `order_count` | integer | ✓ |  |
| `gross_sales` | number | ✓ |  |
| `item_cogs` | number | ✓ |  |
| `gross_profit` | number | ✓ |  |
| `platform_fees` | number | ✓ |  |
| `shipping_costs` | number | ✓ |  |
| `contribution_margin` | number | ✓ |  |

---

### `ClaimCreate` <a id="schema-claimcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `payer_kind` | enum("owner", "employee", "contractor") |  | default `'owner'` |
| `payer_name` | string | ✓ | max 200 |
| `notes` | string \| null |  |  |
| `lines` | [`app__api__v1__endpoints__expense_claims__LineIn`](#schema-app__api__v1__endpoints__expense_claims__linein)[] | ✓ |  |

---

### `ClaimResponse` <a id="schema-claimresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `claim_number` | string | ✓ |  |
| `payer_kind` | string | ✓ |  |
| `payer_name` | string | ✓ |  |
| `submitted_on` | string(date) \| null | ✓ |  |
| `status` | string | ✓ |  |
| `total_amount` | string | ✓ |  |
| `journal_entry_id` | string(uuid) \| null | ✓ |  |
| `reimbursement_journal_entry_id` | string(uuid) \| null | ✓ |  |
| `bill_id` | string(uuid) \| null |  |  |
| `notes` | string \| null | ✓ |  |
| `created_at` | string(date-time) | ✓ |  |
| `lines` | [`LineOut`](#schema-lineout)[] | ✓ |  |

---

### `ConsumptionOut` <a id="schema-consumptionout"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `kind` | string | ✓ |  |
| `material_id` | string(uuid) \| null | ✓ |  |
| `supply_id` | string(uuid) \| null | ✓ |  |
| `product_id` | string(uuid) \| null | ✓ |  |
| `planned_qty` | string | ✓ |  |
| `actual_qty` | string \| null | ✓ |  |
| `actual_unit_cost` | string \| null | ✓ |  |
| `actual_total_cost` | string \| null | ✓ |  |

---

### `CreateFromLineBody` <a id="schema-createfromlinebody"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `statement_line_id` | string(uuid) | ✓ |  |
| `name` | string | ✓ | max 120 |
| `action` | enum("ignore", "create_journal_entry", "create_receipt", "create_payment", "create_inter_account_transfer") |  | default `'ignore'` |
| `category_account_id` | string(uuid) \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `vendor_id` | string(uuid) \| null |  |  |
| `transfer_to_account_id` | string(uuid) \| null |  |  |
| `counterparty_name` | string \| null |  |  |

---

### `CreateTxRequest` <a id="schema-createtxrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `target_account_id` | string(uuid) | ✓ |  |
| `description` | string \| null |  |  |

---

### `CreditNoteCreate` <a id="schema-creditnotecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `customer_id` | string(uuid) | ✓ |  |
| `issued_on` | string(date) | ✓ |  |
| `original_invoice_id` | string(uuid) \| null |  |  |
| `reason` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `lines` | [`app__api__v1__endpoints__notes__LineIn`](#schema-app__api__v1__endpoints__notes__linein)[] | ✓ |  |

---

### `CustomerCreate` <a id="schema-customercreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 200 |
| `email` | string(email) \| null |  |  |
| `phone` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `late_payment_fee_rate_pct` | number \| string \| null |  |  |
| `late_payment_fee_grace_days` | integer \| null |  |  |
| `withholding_profile_id` | string(uuid) \| null |  |  |

---

### `CustomerCreditApply` <a id="schema-customercreditapply"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `amount` | number \| string | ✓ |  |

---

### `CustomerCreditCreate` <a id="schema-customercreditcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `customer_id` | string(uuid) | ✓ |  |
| `invoice_id` | string(uuid) \| null |  |  |
| `credit_date` | string(date) | ✓ |  |
| `amount` | number \| string | ✓ |  |
| `reason` | string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `CustomerCreditResponse` <a id="schema-customercreditresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `customer_id` | string(uuid) | ✓ |  |
| `invoice_id` | string(uuid) \| null |  |  |
| `credit_date` | string(date) | ✓ |  |
| `amount` | string | ✓ |  |
| `remaining_amount` | string | ✓ |  |
| `reason` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `CustomerResponse` <a id="schema-customerresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `email` | string \| null |  |  |
| `phone` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `late_payment_fee_rate_pct` | string \| null |  |  |
| `late_payment_fee_grace_days` | integer \| null |  |  |
| `withholding_profile_id` | string(uuid) \| null |  |  |
| `job_count` | integer |  | default `0` |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `CustomerUpdate` <a id="schema-customerupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `email` | string(email) \| null |  |  |
| `phone` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `late_payment_fee_rate_pct` | number \| string \| null |  |  |
| `late_payment_fee_grace_days` | integer \| null |  |  |
| `withholding_profile_id` | string(uuid) \| null |  |  |

---

### `DNCreate` <a id="schema-dncreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `invoice_id` | string(uuid) \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `issued_on` | string(date) | ✓ |  |
| `shipped_on` | string(date) \| null |  |  |
| `tracking_number` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `lines` | [`app__api__v1__endpoints__delivery_notes__LineIn`](#schema-app__api__v1__endpoints__delivery_notes__linein)[] | ✓ |  |

---

### `DNUpdate` <a id="schema-dnupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `shipped_on` | string(date) \| null |  |  |
| `tracking_number` | string \| null |  |  |
| `status` | enum("draft", "shipped", "delivered", "cancelled") \| null |  |  |
| `notes` | string \| null |  |  |

---

### `DashboardSummary` <a id="schema-dashboardsummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `total_jobs` | integer | ✓ |  |
| `total_pieces` | integer | ✓ |  |
| `total_revenue` | number | ✓ |  |
| `total_costs` | number | ✓ |  |
| `total_platform_fees` | number | ✓ |  |
| `total_net_profit` | number | ✓ |  |
| `avg_profit_per_piece` | number | ✓ |  |
| `avg_margin_pct` | number | ✓ |  |
| `top_material` | string \| null |  |  |

---

### `DebitNoteCreate` <a id="schema-debitnotecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `vendor_id` | string(uuid) | ✓ |  |
| `issued_on` | string(date) | ✓ |  |
| `original_bill_id` | string(uuid) \| null |  |  |
| `reason` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `lines` | [`app__api__v1__endpoints__notes__LineIn`](#schema-app__api__v1__endpoints__notes__linein)[] | ✓ |  |

---

### `DefaultFulfillmentLocationResponse` <a id="schema-defaultfulfillmentlocationresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `location_id` | string(uuid) \| null | ✓ |  |

---

### `DefaultFulfillmentLocationUpdate` <a id="schema-defaultfulfillmentlocationupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `location_id` | string(uuid) \| null |  |  |

---

### `DefinitionCreate` <a id="schema-definitioncreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `scope` | string | ✓ | max 40 |
| `key` | string | ✓ | max 64 |
| `name` | string | ✓ | max 120 |
| `field_type` | enum("text", "long_text", "number", "date", "dropdown", "checkbox", "multi_select", "computed") | ✓ |  |
| `options` | string[] \| null |  |  |
| `is_required` | boolean |  | default `False` |
| `sort_order` | integer |  | default `100` |
| `formula` | string \| null |  |  |

---

### `DefinitionResponse` <a id="schema-definitionresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `scope` | string | ✓ |  |
| `key` | string | ✓ |  |
| `name` | string | ✓ |  |
| `field_type` | string | ✓ |  |
| `options` | string[] \| null | ✓ |  |
| `is_required` | boolean | ✓ |  |
| `sort_order` | integer | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `formula` | string \| null |  |  |

---

### `DefinitionUpdate` <a id="schema-definitionupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `options` | string[] \| null |  |  |
| `is_required` | boolean \| null |  |  |
| `sort_order` | integer \| null |  |  |
| `is_active` | boolean \| null |  |  |
| `formula` | string \| null |  |  |

---

### `DepreciationPostRequest` <a id="schema-depreciationpostrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `period_end` | string(date) | ✓ |  |
| `asset_ids` | string(uuid)[] \| null |  |  |

---

### `DisposeRequest` <a id="schema-disposerequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `disposed_on` | string(date) | ✓ |  |
| `proceeds` | number \| string \| null |  |  |
| `proceeds_account_id` | string(uuid) \| null |  |  |

---

### `DivisionCreate` <a id="schema-divisioncreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `notes` | string \| null |  |  |

---

### `DivisionResponse` <a id="schema-divisionresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `notes` | string \| null | ✓ |  |

---

### `DivisionUpdate` <a id="schema-divisionupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `is_active` | boolean \| null |  |  |
| `notes` | string \| null |  |  |

---

### `DryRunResponse` <a id="schema-dryrunresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `sale_id` | string(uuid) | ✓ |  |
| `snapshot_cogs` | string | ✓ |  |
| `fifo_cogs` | string | ✓ |  |
| `fifo_from_layers` | string | ✓ |  |
| `fifo_from_snapshot` | string | ✓ |  |
| `variance` | string | ✓ |  |

---

### `EmailDeliveryResponse` <a id="schema-emaildeliveryresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `scope` | string | ✓ |  |
| `record_id` | string(uuid) | ✓ |  |
| `to_email` | string | ✓ |  |
| `from_email` | string | ✓ |  |
| `from_name` | string | ✓ |  |
| `subject` | string | ✓ |  |
| `transport` | string | ✓ |  |
| `provider_message_id` | string \| null | ✓ |  |
| `status` | string | ✓ |  |
| `sent_at` | string \| null | ✓ |  |
| `error` | string \| null | ✓ |  |

---

### `EmailSendRequest` <a id="schema-emailsendrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `to_email` | string(email) \| null |  |  |
| `cc` | string(email)[] |  |  |
| `bcc` | string(email)[] |  |  |
| `subject_override` | string \| null |  |  |

---

### `ExpenseCategoryCreate` <a id="schema-expensecategorycreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `description` | string \| null |  |  |
| `account_id` | string(uuid) | ✓ |  |
| `is_active` | boolean |  | default `True` |

---

### `ExpenseCategoryResponse` <a id="schema-expensecategoryresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `description` | string \| null |  |  |
| `account_id` | string(uuid) | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `created_at` | string(date-time) | ✓ |  |
| `updated_at` | string(date-time) | ✓ |  |

---

### `ExpenseCategoryUpdate` <a id="schema-expensecategoryupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `description` | string \| null |  |  |
| `account_id` | string(uuid) \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `ExpenseSummaryRow` <a id="schema-expensesummaryrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `key` | string | ✓ |  |
| `label` | string | ✓ |  |
| `total_amount` | string | ✓ |  |
| `bill_count` | integer | ✓ |  |

---

### `FifoFlagResponse` <a id="schema-fifoflagresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `enabled` | boolean | ✓ |  |

---

### `FifoFlagUpdate` <a id="schema-fifoflagupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `enabled` | boolean | ✓ |  |

---

### `FilamentResolveRequest` <a id="schema-filamentresolverequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `brand` | string \| null |  |  |
| `color` | string \| null |  |  |
| `spool_id` | string \| null |  |  |
| `source` | string |  | default `'print_job'`; print_job | slicer_metadata | printer_telemetry | csv_import | opening_balance |
| `source_printer_id` | string \| null |  |  |
| `source_job_id` | string \| null |  |  |
| `spool_weight_g` | number \| string \| null |  |  |
| `spool_price` | number \| string \| null |  |  |
| `net_usable_g` | number \| string \| null |  |  |
| `cost_per_g` | number \| string \| null |  |  |

---

### `FinanceDashboardSummary` <a id="schema-financedashboardsummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `cash_on_hand` | string | ✓ |  |
| `unpaid_invoices` | string | ✓ |  |
| `unpaid_bills` | string | ✓ |  |
| `current_month_net_income` | string | ✓ |  |
| `inventory_asset_value` | string | ✓ |  |
| `tax_payable` | string | ✓ |  |
| `payouts_in_transit` | string | ✓ |  |

---

### `FixedAssetCreate` <a id="schema-fixedassetcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `asset_tag` | string \| null |  |  |
| `description` | string \| null |  |  |
| `acquired_on` | string(date) | ✓ |  |
| `acquisition_cost` | number \| string | ✓ |  |
| `salvage_value` | number \| string |  | default `0` |
| `useful_life_months` | integer | ✓ |  |
| `depreciation_method` | enum("straight_line", "declining_balance") |  | default `'straight_line'` |
| `declining_balance_rate` | number \| string \| null |  |  |
| `asset_account_id` | string(uuid) \| null |  |  |
| `accumulated_depreciation_account_id` | string(uuid) \| null |  |  |
| `depreciation_expense_account_id` | string(uuid) \| null |  |  |
| `acquisition_bill_id` | string(uuid) \| null |  |  |
| `notes` | string \| null |  |  |

---

### `FixedAssetDetail` <a id="schema-fixedassetdetail"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `asset_tag` | string \| null | ✓ |  |
| `description` | string \| null | ✓ |  |
| `acquired_on` | string(date) | ✓ |  |
| `acquisition_cost` | string | ✓ |  |
| `salvage_value` | string | ✓ |  |
| `useful_life_months` | integer | ✓ |  |
| `depreciation_method` | string | ✓ |  |
| `declining_balance_rate` | string \| null | ✓ |  |
| `asset_account_id` | string(uuid) | ✓ |  |
| `accumulated_depreciation_account_id` | string(uuid) | ✓ |  |
| `depreciation_expense_account_id` | string(uuid) | ✓ |  |
| `status` | string | ✓ |  |
| `disposed_on` | string(date) \| null | ✓ |  |
| `disposal_proceeds` | string \| null | ✓ |  |
| `disposal_journal_entry_id` | string(uuid) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `book_value` | string | ✓ |  |
| `schedule` | [`ScheduleRow`](#schema-schedulerow)[] | ✓ |  |
| `posted_periods` | string(date)[] | ✓ |  |

---

### `FixedAssetResponse` <a id="schema-fixedassetresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `asset_tag` | string \| null | ✓ |  |
| `description` | string \| null | ✓ |  |
| `acquired_on` | string(date) | ✓ |  |
| `acquisition_cost` | string | ✓ |  |
| `salvage_value` | string | ✓ |  |
| `useful_life_months` | integer | ✓ |  |
| `depreciation_method` | string | ✓ |  |
| `declining_balance_rate` | string \| null | ✓ |  |
| `asset_account_id` | string(uuid) | ✓ |  |
| `accumulated_depreciation_account_id` | string(uuid) | ✓ |  |
| `depreciation_expense_account_id` | string(uuid) | ✓ |  |
| `status` | string | ✓ |  |
| `disposed_on` | string(date) \| null | ✓ |  |
| `disposal_proceeds` | string \| null | ✓ |  |
| `disposal_journal_entry_id` | string(uuid) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `book_value` | string | ✓ |  |

---

### `FixedAssetUpdate` <a id="schema-fixedassetupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `asset_tag` | string \| null |  |  |
| `description` | string \| null |  |  |
| `acquisition_cost` | number \| string \| null |  |  |
| `salvage_value` | number \| string \| null |  |  |
| `useful_life_months` | integer \| null |  |  |
| `depreciation_method` | enum("straight_line", "declining_balance") \| null |  |  |
| `declining_balance_rate` | number \| string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `HTTPValidationError` <a id="schema-httpvalidationerror"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `detail` | [`ValidationError`](#schema-validationerror)[] |  |  |

---

### `InsightEvidenceMetric` <a id="schema-insightevidencemetric"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `key` | string | ✓ |  |
| `label` | string | ✓ |  |
| `value` | string | ✓ |  |

---

### `InsightItem` <a id="schema-insightitem"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `title` | string | ✓ |  |
| `detail` | string | ✓ |  |
| `priority` | enum("high", "medium", "low") |  | default `'medium'` |
| `evidence` | string[] |  |  |
| `recommended_action` | string \| null |  |  |

---

### `InsightRequest` <a id="schema-insightrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `question` | string \| null |  | Optional operator question to steer the insight summary. |

---

### `InsightStatusResponse` <a id="schema-insightstatusresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `provider` | enum("chatgpt", "claude", "grok") | ✓ |  |
| `model` | string | ✓ |  |
| `configured` | boolean | ✓ |  |
| `available_providers` | enum("chatgpt", "claude", "grok")[] | ✓ |  |
| `note` | string | ✓ |  |

---

### `InsightSummaryResponse` <a id="schema-insightsummaryresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `provider` | enum("chatgpt", "claude", "grok") | ✓ |  |
| `model` | string | ✓ |  |
| `generated_at` | string(date-time) | ✓ |  |
| `title` | string | ✓ |  |
| `summary` | string | ✓ |  |
| `question` | string \| null |  |  |
| `recommendations` | [`InsightItem`](#schema-insightitem)[] | ✓ |  |
| `risks` | [`InsightItem`](#schema-insightitem)[] | ✓ |  |
| `suggested_questions` | string[] | ✓ |  |
| `evidence_metrics` | [`InsightEvidenceMetric`](#schema-insightevidencemetric)[] | ✓ |  |
| `read_only` | boolean |  | default `True` |

---

### `IntangibleAssetCreate` <a id="schema-intangibleassetcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `asset_tag` | string \| null |  |  |
| `description` | string \| null |  |  |
| `acquired_on` | string(date) | ✓ |  |
| `acquisition_cost` | number \| string | ✓ |  |
| `salvage_value` | number \| string |  | default `0` |
| `useful_life_months` | integer | ✓ |  |
| `amortization_method` | enum("straight_line", "declining_balance") |  | default `'straight_line'` |
| `declining_balance_rate` | number \| string \| null |  |  |
| `asset_account_id` | string(uuid) \| null |  |  |
| `accumulated_amortization_account_id` | string(uuid) \| null |  |  |
| `amortization_expense_account_id` | string(uuid) \| null |  |  |
| `notes` | string \| null |  |  |

---

### `IntangibleAssetDetail` <a id="schema-intangibleassetdetail"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `asset_tag` | string \| null | ✓ |  |
| `description` | string \| null | ✓ |  |
| `acquired_on` | string(date) | ✓ |  |
| `acquisition_cost` | string | ✓ |  |
| `salvage_value` | string | ✓ |  |
| `useful_life_months` | integer | ✓ |  |
| `amortization_method` | string | ✓ |  |
| `declining_balance_rate` | string \| null | ✓ |  |
| `asset_account_id` | string(uuid) | ✓ |  |
| `accumulated_amortization_account_id` | string(uuid) | ✓ |  |
| `amortization_expense_account_id` | string(uuid) | ✓ |  |
| `status` | string | ✓ |  |
| `disposed_on` | string(date) \| null | ✓ |  |
| `disposal_proceeds` | string \| null | ✓ |  |
| `disposal_journal_entry_id` | string(uuid) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `book_value` | string | ✓ |  |
| `schedule` | [`ScheduleRow`](#schema-schedulerow)[] | ✓ |  |
| `posted_periods` | string(date)[] | ✓ |  |

---

### `IntangibleAssetResponse` <a id="schema-intangibleassetresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `asset_tag` | string \| null | ✓ |  |
| `description` | string \| null | ✓ |  |
| `acquired_on` | string(date) | ✓ |  |
| `acquisition_cost` | string | ✓ |  |
| `salvage_value` | string | ✓ |  |
| `useful_life_months` | integer | ✓ |  |
| `amortization_method` | string | ✓ |  |
| `declining_balance_rate` | string \| null | ✓ |  |
| `asset_account_id` | string(uuid) | ✓ |  |
| `accumulated_amortization_account_id` | string(uuid) | ✓ |  |
| `amortization_expense_account_id` | string(uuid) | ✓ |  |
| `status` | string | ✓ |  |
| `disposed_on` | string(date) \| null | ✓ |  |
| `disposal_proceeds` | string \| null | ✓ |  |
| `disposal_journal_entry_id` | string(uuid) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `book_value` | string | ✓ |  |

---

### `IntangibleAssetUpdate` <a id="schema-intangibleassetupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `asset_tag` | string \| null |  |  |
| `description` | string \| null |  |  |
| `acquisition_cost` | number \| string \| null |  |  |
| `salvage_value` | number \| string \| null |  |  |
| `useful_life_months` | integer \| null |  |  |
| `amortization_method` | enum("straight_line", "declining_balance") \| null |  |  |
| `declining_balance_rate` | number \| string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `InventoryAlert` <a id="schema-inventoryalert"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `type` | string | ✓ |  |
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `sku` | string \| null |  |  |
| `current_stock` | string \| integer | ✓ |  |
| `reorder_point` | string \| integer | ✓ |  |

---

### `InventoryReconcileRequest` <a id="schema-inventoryreconcilerequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string(uuid) | ✓ |  |
| `counted_qty` | integer | ✓ | ≥ 0.0 |
| `reason` | string | ✓ | max 255 |
| `notes` | string \| null |  |  |

---

### `InventoryReconcileResponse` <a id="schema-inventoryreconcileresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string(uuid) | ✓ |  |
| `current_qty` | integer | ✓ |  |
| `counted_qty` | integer | ✓ |  |
| `variance` | integer | ✓ |  |
| `approval_required` | boolean |  | default `False` |
| `detail` | string | ✓ |  |
| `transaction` | [`InventoryTransactionResponse`](#schema-inventorytransactionresponse) \| null |  |  |

---

### `InventoryReportResponse` <a id="schema-inventoryreportresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `stock_levels` | [`StockLevelRow`](#schema-stocklevelrow)[] | ✓ |  |
| `total_stock_value` | number | ✓ |  |
| `total_products` | integer | ✓ |  |
| `low_stock_count` | integer | ✓ |  |
| `material_usage` | object[] | ✓ |  |
| `turnover` | object[] | ✓ |  |

---

### `InventoryTransactionCreate` <a id="schema-inventorytransactioncreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string(uuid) | ✓ |  |
| `type` | [`TransactionType`](#schema-transactiontype) | ✓ |  |
| `quantity` | integer | ✓ | Positive to add, negative to remove |
| `unit_cost` | number \| string |  | default `'0'` |
| `notes` | string \| null |  |  |

---

### `InventoryTransactionResponse` <a id="schema-inventorytransactionresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `product_id` | string(uuid) | ✓ |  |
| `product_name` | string \| null |  |  |
| `product_sku` | string \| null |  |  |
| `job_id` | string(uuid) \| null |  |  |
| `type` | string | ✓ |  |
| `quantity` | integer | ✓ |  |
| `unit_cost` | string | ✓ |  |
| `notes` | string \| null |  |  |
| `created_by` | string(uuid) \| null |  |  |
| `created_by_name` | string \| null |  |  |
| `created_at` | string(date-time) \| null |  |  |

---

### `InventoryValuationRow` <a id="schema-inventoryvaluationrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `material_id` | string | ✓ |  |
| `material_name` | string | ✓ |  |
| `receipt_id` | string | ✓ |  |
| `vendor_name` | string | ✓ |  |
| `purchase_date` | string(date) | ✓ |  |
| `quantity_remaining_g` | string | ✓ |  |
| `landed_cost_per_g` | string | ✓ |  |
| `remaining_value` | string | ✓ |  |

---

### `InventoryValuationSummary` <a id="schema-inventoryvaluationsummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `rows` | [`InventoryValuationRow`](#schema-inventoryvaluationrow)[] | ✓ |  |
| `total_inventory_value` | string | ✓ |  |
| `total_quantity_remaining_g` | string | ✓ |  |

---

### `InvoiceCreate` <a id="schema-invoicecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `invoice_number` | string \| null |  |  |
| `quote_id` | string(uuid) \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `issue_date` | string(date) | ✓ |  |
| `due_date` | string(date) \| null |  |  |
| `tax_amount` | number \| string |  | default `0` |
| `tax_profile_id` | string(uuid) \| null |  |  |
| `shipping_amount` | number \| string |  | default `0` |
| `credits_applied` | number \| string |  | default `0` |
| `notes` | string \| null |  |  |
| `status` | [`InvoiceStatus`](#schema-invoicestatus) |  | default `'draft'` |
| `lines` | [`InvoiceLineCreate`](#schema-invoicelinecreate)[] |  |  |

---

### `InvoiceFromQuoteCreate` <a id="schema-invoicefromquotecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `invoice_number` | string \| null |  |  |
| `issue_date` | string(date) | ✓ |  |
| `due_date` | string(date) \| null |  |  |
| `tax_amount` | number \| string |  | default `0` |
| `shipping_amount` | number \| string \| null |  |  |
| `credits_applied` | number \| string |  | default `0` |
| `notes` | string \| null |  |  |
| `status` | [`InvoiceStatus`](#schema-invoicestatus) |  | default `'draft'` |

---

### `InvoiceLineCreate` <a id="schema-invoicelinecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `description` | string | ✓ | max 255 |
| `quantity` | integer | ✓ |  |
| `unit_price` | number \| string | ✓ |  |
| `notes` | string \| null |  |  |

---

### `InvoiceLineResponse` <a id="schema-invoicelineresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `invoice_id` | string(uuid) | ✓ |  |
| `description` | string | ✓ |  |
| `quantity` | integer | ✓ |  |
| `unit_price` | string | ✓ |  |
| `line_total` | string | ✓ |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `InvoicePaymentApply` <a id="schema-invoicepaymentapply"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `amount` | number \| string | ✓ |  |
| `paid_at` | string(date) \| null |  |  |

---

### `InvoiceResponse` <a id="schema-invoiceresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `invoice_number` | string | ✓ |  |
| `quote_id` | string(uuid) \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `issue_date` | string(date) | ✓ |  |
| `due_date` | string(date) \| null |  |  |
| `subtotal` | string | ✓ |  |
| `tax_amount` | string | ✓ |  |
| `shipping_amount` | string | ✓ |  |
| `credits_applied` | string | ✓ |  |
| `total_due` | string | ✓ |  |
| `amount_paid` | string | ✓ |  |
| `balance_due` | string | ✓ |  |
| `status` | string | ✓ |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |
| `updated_at` | string(date-time) | ✓ |  |
| `lines` | [`InvoiceLineResponse`](#schema-invoicelineresponse)[] |  | default `[]` |

---

### `InvoiceStatus` <a id="schema-invoicestatus"></a>

_Type: enum("draft", "sent", "partially_paid", "paid", "overdue", "void")_

---

### `InvoiceUpdate` <a id="schema-invoiceupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `due_date` | string(date) \| null |  |  |
| `tax_amount` | number \| string \| null |  |  |
| `shipping_amount` | number \| string \| null |  |  |
| `credits_applied` | number \| string \| null |  |  |
| `notes` | string \| null |  |  |
| `status` | [`InvoiceStatus`](#schema-invoicestatus) \| null |  |  |

---

### `JobCreate` <a id="schema-jobcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `job_number` | string \| null |  |  |
| `date` | string(date) | ✓ |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `product_name` | string | ✓ | max 200 |
| `qty_per_plate` | integer \| null |  |  |
| `num_plates` | integer \| null |  |  |
| `material_id` | string(uuid) | ✓ |  |
| `material_per_plate_g` | number \| string \| null |  |  |
| `print_time_per_plate_hrs` | number \| string \| null |  |  |
| `labor_mins` | number \| string |  | default `'0'` |
| `design_time_hrs` | number \| string \| null |  | default `'0'` |
| `shipping_cost` | number \| string |  | default `'0'` |
| `target_margin_pct` | number \| string |  | default `'40'` |
| `product_id` | string(uuid) \| null |  |  |
| `printer_id` | string(uuid) \| null |  |  |
| `project_id` | string(uuid) \| null |  |  |
| `status` | [`JobStatus`](#schema-jobstatus) |  | default `'completed'` |
| `plates` | [`PlateIn`](#schema-platein)[] \| null |  | Per-plate breakdown for multi-part prints. If provided, supersedes uniform fields. |

---

### `JobResponse` <a id="schema-jobresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `job_number` | string | ✓ |  |
| `date` | string(date) | ✓ |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `product_name` | string | ✓ |  |
| `qty_per_plate` | integer \| null |  |  |
| `num_plates` | integer \| null |  |  |
| `material_id` | string(uuid) | ✓ |  |
| `total_pieces` | integer | ✓ |  |
| `material_per_plate_g` | string \| null |  |  |
| `print_time_per_plate_hrs` | string \| null |  |  |
| `total_material_g` | string | ✓ |  |
| `total_print_time_hrs` | string | ✓ |  |
| `labor_mins` | string | ✓ |  |
| `design_time_hrs` | string \| null |  |  |
| `electricity_cost` | string | ✓ |  |
| `material_cost` | string | ✓ |  |
| `labor_cost` | string | ✓ |  |
| `design_cost` | string | ✓ |  |
| `machine_cost` | string | ✓ |  |
| `packaging_cost` | string | ✓ |  |
| `shipping_cost` | string | ✓ |  |
| `failure_buffer` | string | ✓ |  |
| `subtotal_cost` | string | ✓ |  |
| `overhead` | string | ✓ |  |
| `total_cost` | string | ✓ |  |
| `cost_per_piece` | string | ✓ |  |
| `target_margin_pct` | string | ✓ |  |
| `price_per_piece` | string | ✓ |  |
| `total_revenue` | string | ✓ |  |
| `platform_fees` | string | ✓ |  |
| `net_profit` | string | ✓ |  |
| `profit_per_piece` | string | ✓ |  |
| `product_id` | string(uuid) \| null |  |  |
| `printer_id` | string(uuid) \| null |  |  |
| `printer` | [`PrinterResponse`](#schema-printerresponse) \| null |  |  |
| `project_id` | string(uuid) \| null |  |  |
| `inventory_added` | boolean |  | default `False` |
| `status` | string | ✓ |  |
| `plates` | [`PlateResponse`](#schema-plateresponse)[] |  | default `[]` |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `JobStatus` <a id="schema-jobstatus"></a>

_Type: enum("draft", "in_progress", "completed", "cancelled")_

---

### `JobUpdate` <a id="schema-jobupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `job_number` | string \| null |  |  |
| `date` | string(date) \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `product_name` | string \| null |  |  |
| `qty_per_plate` | integer \| null |  |  |
| `num_plates` | integer \| null |  |  |
| `material_id` | string(uuid) \| null |  |  |
| `material_per_plate_g` | number \| string \| null |  |  |
| `print_time_per_plate_hrs` | number \| string \| null |  |  |
| `labor_mins` | number \| string \| null |  |  |
| `design_time_hrs` | number \| string \| null |  |  |
| `shipping_cost` | number \| string \| null |  |  |
| `target_margin_pct` | number \| string \| null |  |  |
| `product_id` | string(uuid) \| null |  |  |
| `printer_id` | string(uuid) \| null |  |  |
| `project_id` | string(uuid) \| null |  |  |
| `status` | [`JobStatus`](#schema-jobstatus) \| null |  |  |
| `plates` | [`PlateIn`](#schema-platein)[] \| null |  |  |

---

### `JournalEntryCreate` <a id="schema-journalentrycreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `entry_date` | string(date) | ✓ |  |
| `accounting_period_id` | string(uuid) \| null |  |  |
| `source_type` | string \| null |  |  |
| `source_id` | string \| null |  |  |
| `memo` | string \| null |  |  |
| `division_id` | string(uuid) \| null |  |  |
| `project_id` | string(uuid) \| null |  |  |
| `lines` | [`JournalLineCreate`](#schema-journallinecreate)[] | ✓ |  |

---

### `JournalEntryResponse` <a id="schema-journalentryresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `entry_number` | string | ✓ |  |
| `entry_date` | string(date) | ✓ |  |
| `accounting_period_id` | string(uuid) \| null |  |  |
| `status` | string | ✓ |  |
| `source_type` | string \| null |  |  |
| `source_id` | string \| null |  |  |
| `memo` | string \| null |  |  |
| `posted_at` | string(date-time) \| null |  |  |
| `is_reversal` | boolean | ✓ |  |
| `reversal_of_id` | string(uuid) \| null |  |  |
| `lines` | [`JournalLineResponse`](#schema-journallineresponse)[] |  | default `[]` |

---

### `JournalEntryReverse` <a id="schema-journalentryreverse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `reversal_date` | string(date) | ✓ |  |
| `memo` | string \| null |  |  |

---

### `JournalLineCreate` <a id="schema-journallinecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `account_id` | string(uuid) | ✓ |  |
| `entry_type` | string | ✓ |  |
| `amount` | number \| string | ✓ |  |
| `description` | string \| null |  |  |

---

### `JournalLineDTO` <a id="schema-journallinedto"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `journal_entry_id` | string(uuid) | ✓ |  |
| `entry_date` | string(date) | ✓ |  |
| `description` | string \| null | ✓ |  |
| `entry_type` | string | ✓ |  |
| `amount` | string | ✓ |  |
| `cleared_status` | string | ✓ |  |

---

### `JournalLineDrillRow` <a id="schema-journallinedrillrow"></a>

#322 P2: one source journal line behind a report cell.

| Field | Type | Req | Notes |
|---|---|---|---|
| `journal_entry_id` | string | ✓ |  |
| `entry_number` | string | ✓ |  |
| `entry_date` | string | ✓ |  |
| `line_id` | string | ✓ |  |
| `account_id` | string | ✓ |  |
| `account_code` | string | ✓ |  |
| `account_name` | string | ✓ |  |
| `entry_type` | string | ✓ |  |
| `amount` | string | ✓ |  |
| `description` | string \| null |  |  |
| `source_type` | string \| null |  |  |
| `source_id` | string \| null |  |  |

---

### `JournalLineResponse` <a id="schema-journallineresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `account_id` | string(uuid) | ✓ |  |
| `line_number` | integer | ✓ |  |
| `entry_type` | string | ✓ |  |
| `amount` | string | ✓ |  |
| `description` | string \| null |  |  |

---

### `JournalLineSuggestion` <a id="schema-journallinesuggestion"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `journal_entry_id` | string(uuid) | ✓ |  |
| `entry_type` | string | ✓ |  |
| `amount` | string | ✓ |  |
| `description` | string \| null | ✓ |  |

---

### `KitComponentResponse` <a id="schema-kitcomponentresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `component_product_id` | string(uuid) | ✓ |  |
| `quantity` | string | ✓ |  |

---

### `KitComponentRow` <a id="schema-kitcomponentrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `component_product_id` | string(uuid) | ✓ |  |
| `quantity` | number \| string | ✓ |  |

---

### `KitDefinitionRequest` <a id="schema-kitdefinitionrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `components` | [`KitComponentRow`](#schema-kitcomponentrow)[] | ✓ |  |

---

### `KitResponse` <a id="schema-kitresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `kit_product_id` | string(uuid) | ✓ |  |
| `components` | [`KitComponentResponse`](#schema-kitcomponentresponse)[] | ✓ |  |

---

### `LineOut` <a id="schema-lineout"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `description` | string | ✓ |  |
| `expense_account_id` | string(uuid) | ✓ |  |
| `amount` | string | ✓ |  |
| `line_kind` | string |  | default `'expense'` |
| `miles` | string \| null |  |  |
| `mileage_rate_used` | string \| null |  |  |
| `notes` | string \| null | ✓ |  |

---

### `LocationCreate` <a id="schema-locationcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `kind` | enum("internal", "consignment", "marketplace") |  | default `'internal'` |
| `notes` | string \| null |  |  |

---

### `LocationResponse` <a id="schema-locationresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `kind` | string | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `notes` | string \| null | ✓ |  |

---

### `LocationStockRow` <a id="schema-locationstockrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string(uuid) | ✓ |  |
| `on_hand_qty` | string | ✓ |  |
| `in_transit_to_qty` | string | ✓ |  |
| `projected_qty` | string | ✓ |  |

---

### `LocationUpdate` <a id="schema-locationupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `kind` | enum("internal", "consignment", "marketplace") \| null |  |  |
| `is_active` | boolean \| null |  |  |
| `notes` | string \| null |  |  |

---

### `LoginRequest` <a id="schema-loginrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `email` | string(email) | ✓ |  |
| `password` | string | ✓ |  |

---

### `MappingResponse` <a id="schema-mappingresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `account_id` | string(uuid) | ✓ |  |
| `mapping` | object<string, string> | ✓ |  |

---

### `MappingUpsertRequest` <a id="schema-mappingupsertrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `mapping` | object<string, string> | ✓ | Keys: date, amount, description, fitid → column names |

---

### `MarketplaceSettlementCreate` <a id="schema-marketplacesettlementcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `settlement_number` | string | ✓ | max 60 |
| `channel_id` | string(uuid) | ✓ |  |
| `period_start` | string(date) | ✓ |  |
| `period_end` | string(date) | ✓ |  |
| `payout_date` | string(date) | ✓ |  |
| `gross_sales` | number \| string |  | default `0` |
| `marketplace_fees` | number \| string |  | default `0` |
| `adjustments` | number \| string |  | default `0` |
| `reserves_held` | number \| string |  | default `0` |
| `net_deposit` | number \| string | ✓ |  |
| `notes` | string \| null |  |  |
| `lines` | [`SettlementLineCreate`](#schema-settlementlinecreate)[] |  |  |

---

### `MarketplaceSettlementResponse` <a id="schema-marketplacesettlementresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `settlement_number` | string | ✓ |  |
| `channel_id` | string(uuid) | ✓ |  |
| `period_start` | string(date) | ✓ |  |
| `period_end` | string(date) | ✓ |  |
| `payout_date` | string(date) | ✓ |  |
| `gross_sales` | string | ✓ |  |
| `marketplace_fees` | string | ✓ |  |
| `adjustments` | string | ✓ |  |
| `reserves_held` | string | ✓ |  |
| `net_deposit` | string | ✓ |  |
| `expected_net` | string | ✓ |  |
| `discrepancy_amount` | string | ✓ |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |
| `updated_at` | string(date-time) | ✓ |  |
| `lines` | [`SettlementLineResponse`](#schema-settlementlineresponse)[] |  | default `[]` |

---

### `MatchRequest` <a id="schema-matchrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `journal_line_id` | string(uuid) | ✓ |  |

---

### `MaterialCreate` <a id="schema-materialcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 50 |
| `brand` | string | ✓ | max 100 |
| `spool_weight_g` | number \| string | ✓ |  |
| `spool_price` | number \| string | ✓ |  |
| `net_usable_g` | number \| string | ✓ |  |
| `notes` | string \| null |  |  |
| `spools_in_stock` | integer |  | default `0`; ≥ 0.0 |
| `reorder_point` | integer |  | default `2`; ≥ 0.0 |
| `active` | boolean |  | default `True` |

---

### `MaterialReceiptCreate` <a id="schema-materialreceiptcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `vendor_name` | string | ✓ | max 120 |
| `purchase_date` | string(date) | ✓ |  |
| `receipt_number` | string \| null |  |  |
| `quantity_purchased_g` | number \| string | ✓ |  |
| `unit_cost_per_g` | number \| string | ✓ |  |
| `landed_cost_total` | number \| string |  | default `0` |
| `valuation_method` | string |  | default `'lot'` |
| `notes` | string \| null |  |  |

---

### `MaterialReceiptResponse` <a id="schema-materialreceiptresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `material_id` | string(uuid) | ✓ |  |
| `vendor_name` | string | ✓ |  |
| `purchase_date` | string(date) | ✓ |  |
| `receipt_number` | string \| null |  |  |
| `quantity_purchased_g` | string | ✓ |  |
| `quantity_remaining_g` | string | ✓ |  |
| `unit_cost_per_g` | string | ✓ |  |
| `landed_cost_total` | string | ✓ |  |
| `landed_cost_per_g` | string | ✓ |  |
| `total_cost` | string | ✓ |  |
| `valuation_method` | string | ✓ |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `MaterialResponse` <a id="schema-materialresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `brand` | string | ✓ |  |
| `spool_weight_g` | string | ✓ |  |
| `spool_price` | string | ✓ |  |
| `net_usable_g` | string | ✓ |  |
| `cost_per_g` | string | ✓ |  |
| `notes` | string \| null |  |  |
| `spools_in_stock` | integer | ✓ |  |
| `reorder_point` | integer | ✓ |  |
| `active` | boolean | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `MaterialUpdate` <a id="schema-materialupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `brand` | string \| null |  |  |
| `spool_weight_g` | number \| string \| null |  |  |
| `spool_price` | number \| string \| null |  |  |
| `net_usable_g` | number \| string \| null |  |  |
| `notes` | string \| null |  |  |
| `spools_in_stock` | integer \| null |  |  |
| `reorder_point` | integer \| null |  |  |
| `active` | boolean \| null |  |  |

---

### `MaterialUsageDataPoint` <a id="schema-materialusagedatapoint"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `material` | string | ✓ |  |
| `count` | integer | ✓ |  |

---

### `MergeRequest` <a id="schema-mergerequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `survivor_id` | string(uuid) | ✓ |  |
| `duplicate_ids` | string(uuid)[] | ✓ |  |

---

### `PLReportResponse` <a id="schema-plreportresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `summary` | [`PLSummary`](#schema-plsummary) | ✓ |  |
| `period_data` | [`PLRow`](#schema-plrow)[] | ✓ |  |

---

### `PLRow` <a id="schema-plrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `period` | string | ✓ |  |
| `sales_revenue` | number | ✓ |  |
| `operational_production_estimate` | number | ✓ |  |
| `material_costs` | number | ✓ |  |
| `labor_costs` | number | ✓ |  |
| `machine_costs` | number | ✓ |  |
| `overhead_costs` | number | ✓ |  |
| `platform_fees` | number | ✓ |  |
| `shipping_costs` | number | ✓ |  |
| `total_costs` | number | ✓ |  |
| `gross_profit` | number | ✓ |  |
| `notes` | string | ✓ |  |

---

### `PLSummary` <a id="schema-plsummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `sales_revenue` | number | ✓ |  |
| `operational_production_estimate` | number | ✓ |  |
| `total_revenue` | number | ✓ |  |
| `material_costs` | number | ✓ |  |
| `labor_costs` | number | ✓ |  |
| `machine_costs` | number | ✓ |  |
| `overhead_costs` | number | ✓ |  |
| `platform_fees` | number | ✓ |  |
| `shipping_costs` | number | ✓ |  |
| `total_costs` | number | ✓ |  |
| `gross_profit` | number | ✓ |  |
| `profit_margin_pct` | number | ✓ |  |
| `reporting_basis` | string | ✓ |  |
| `production_estimate_note` | string | ✓ |  |

---

### `PODetail` <a id="schema-podetail"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `order_number` | string | ✓ |  |
| `product_id` | string(uuid) | ✓ |  |
| `output_quantity` | string | ✓ |  |
| `status` | string | ✓ |  |
| `planned_start_date` | string(date) \| null | ✓ |  |
| `completed_at` | string(date-time) \| null | ✓ |  |
| `total_material_cost` | string \| null | ✓ |  |
| `applied_overhead` | string \| null | ✓ |  |
| `total_finished_goods_value` | string \| null | ✓ |  |
| `journal_entry_id` | string(uuid) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `consumptions` | [`ConsumptionOut`](#schema-consumptionout)[] | ✓ |  |

---

### `POResponse` <a id="schema-poresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `order_number` | string | ✓ |  |
| `product_id` | string(uuid) | ✓ |  |
| `output_quantity` | string | ✓ |  |
| `status` | string | ✓ |  |
| `planned_start_date` | string(date) \| null | ✓ |  |
| `completed_at` | string(date-time) \| null | ✓ |  |
| `total_material_cost` | string \| null | ✓ |  |
| `applied_overhead` | string \| null | ✓ |  |
| `total_finished_goods_value` | string \| null | ✓ |  |
| `journal_entry_id` | string(uuid) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |

---

### `POSCheckoutCreate` <a id="schema-poscheckoutcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `date` | string(date) | ✓ |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `tax_profile_id` | string(uuid) \| null |  |  |
| `tax_treatment` | string |  | default `'seller_collected'` |
| `tax_collected` | number \| string |  | default `'0'` |
| `payment_method` | string | ✓ | max 50 |
| `notes` | string \| null |  |  |
| `items` | [`SaleItemCreate`](#schema-saleitemcreate)[] | ✓ |  |

---

### `POSProductScanRequest` <a id="schema-posproductscanrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `code` | string | ✓ | max 64 |

---

### `PaginatedCameras` <a id="schema-paginatedcameras"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `items` | [`CameraResponse`](#schema-cameraresponse)[] | ✓ |  |
| `total` | integer | ✓ |  |
| `skip` | integer | ✓ |  |
| `limit` | integer | ✓ |  |

---

### `PaginatedInvoices` <a id="schema-paginatedinvoices"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `items` | [`InvoiceResponse`](#schema-invoiceresponse)[] | ✓ |  |
| `total` | integer | ✓ |  |
| `skip` | integer | ✓ |  |
| `limit` | integer | ✓ |  |

---

### `PaginatedJobs` <a id="schema-paginatedjobs"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `items` | [`JobResponse`](#schema-jobresponse)[] | ✓ |  |
| `total` | integer | ✓ |  |
| `skip` | integer | ✓ |  |
| `limit` | integer | ✓ |  |

---

### `PaginatedPrinters` <a id="schema-paginatedprinters"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `items` | [`PrinterResponse`](#schema-printerresponse)[] | ✓ |  |
| `total` | integer | ✓ |  |
| `skip` | integer | ✓ |  |
| `limit` | integer | ✓ |  |

---

### `PaginatedProducts` <a id="schema-paginatedproducts"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `items` | [`ProductResponse`](#schema-productresponse)[] | ✓ |  |
| `total` | integer | ✓ |  |
| `skip` | integer | ✓ |  |
| `limit` | integer | ✓ |  |

---

### `PaginatedQuotes` <a id="schema-paginatedquotes"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `items` | [`QuoteResponse`](#schema-quoteresponse)[] | ✓ |  |
| `total` | integer | ✓ |  |
| `skip` | integer | ✓ |  |
| `limit` | integer | ✓ |  |

---

### `PaginatedSales` <a id="schema-paginatedsales"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `items` | [`SaleListResponse`](#schema-salelistresponse)[] | ✓ |  |
| `total` | integer | ✓ |  |
| `skip` | integer | ✓ |  |
| `limit` | integer | ✓ |  |

---

### `PaginatedTransactions` <a id="schema-paginatedtransactions"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `items` | [`InventoryTransactionResponse`](#schema-inventorytransactionresponse)[] | ✓ |  |
| `total` | integer | ✓ |  |
| `skip` | integer | ✓ |  |
| `limit` | integer | ✓ |  |

---

### `PasswordChange` <a id="schema-passwordchange"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `current_password` | string | ✓ |  |
| `new_password` | string | ✓ | max 128 |

---

### `PaymentCreate` <a id="schema-paymentcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `customer_id` | string(uuid) \| null |  |  |
| `invoice_id` | string(uuid) \| null |  |  |
| `payment_date` | string(date) | ✓ |  |
| `amount` | number \| string | ✓ |  |
| `payment_method` | string \| null |  |  |
| `reference_number` | string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `PaymentMethodBreakdown` <a id="schema-paymentmethodbreakdown"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `payment_method` | string | ✓ |  |
| `order_count` | integer | ✓ |  |
| `gross_sales` | number | ✓ |  |
| `contribution_margin` | number | ✓ |  |

---

### `PaymentResponse` <a id="schema-paymentresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `customer_id` | string(uuid) \| null |  |  |
| `invoice_id` | string(uuid) \| null |  |  |
| `payment_date` | string(date) | ✓ |  |
| `amount` | string | ✓ |  |
| `payment_method` | string \| null |  |  |
| `reference_number` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `unapplied_amount` | string | ✓ |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `PeriodCloseDateResponse` <a id="schema-periodclosedateresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `close_date` | string(date) \| null | ✓ |  |

---

### `PeriodCloseDateUpdate` <a id="schema-periodclosedateupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `close_date` | string(date) \| null |  |  |

---

### `PlateIn` <a id="schema-platein"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `plate_number` | integer \| null |  |  |
| `printer_id` | string(uuid) \| null |  |  |
| `parts_count` | integer | ✓ |  |
| `material_g` | number \| string | ✓ |  |
| `print_time_hrs` | number \| string | ✓ |  |

---

### `PlateResponse` <a id="schema-plateresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `plate_number` | integer | ✓ |  |
| `printer_id` | string(uuid) \| null |  |  |
| `parts_count` | integer | ✓ |  |
| `material_g` | string | ✓ |  |
| `print_time_hrs` | string | ✓ |  |

---

### `PreventNegativeStockResponse` <a id="schema-preventnegativestockresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `enabled` | boolean | ✓ |  |

---

### `PreventNegativeStockUpdate` <a id="schema-preventnegativestockupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `enabled` | boolean | ✓ |  |

---

### `PrinterConnectionTestResponse` <a id="schema-printerconnectiontestresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `ok` | boolean | ✓ |  |
| `provider` | string | ✓ |  |
| `normalized_status` | string \| null |  |  |
| `online` | boolean \| null |  |  |
| `message` | string \| null |  |  |

---

### `PrinterCreate` <a id="schema-printercreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `slug` | string | ✓ | max 120 |
| `manufacturer` | string \| null |  |  |
| `model` | string \| null |  |  |
| `serial_number` | string \| null |  |  |
| `location` | string \| null |  |  |
| `status` | [`PrinterStatus`](#schema-printerstatus) |  | default `'idle'` |
| `is_active` | boolean |  | default `True` |
| `notes` | string \| null |  |  |
| `monitor_enabled` | boolean |  | default `False` |
| `monitor_provider` | [`PrinterMonitorProvider`](#schema-printermonitorprovider) \| null |  |  |
| `monitor_base_url` | string \| null |  |  |
| `monitor_api_key` | string \| null |  |  |
| `monitor_poll_interval_seconds` | integer |  | default `30`; ≥ 5.0; ≤ 3600.0 |

---

### `PrinterHistoryEventResponse` <a id="schema-printerhistoryeventresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `printer_id` | string(uuid) | ✓ |  |
| `job_id` | string(uuid) \| null |  |  |
| `actor_user_id` | string(uuid) \| null |  |  |
| `actor_name` | string \| null |  |  |
| `event_type` | string | ✓ |  |
| `title` | string | ✓ |  |
| `description` | string \| null |  |  |
| `metadata` | object \| null |  |  |
| `created_at` | string(date-time) \| null |  |  |

---

### `PrinterMonitorProvider` <a id="schema-printermonitorprovider"></a>

_Type: enum("octoprint", "moonraker")_

---

### `PrinterResponse` <a id="schema-printerresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `slug` | string | ✓ |  |
| `manufacturer` | string \| null |  |  |
| `model` | string \| null |  |  |
| `serial_number` | string \| null |  |  |
| `location` | string \| null |  |  |
| `status` | string | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `notes` | string \| null |  |  |
| `monitor_enabled` | boolean | ✓ |  |
| `monitor_provider` | string \| null |  |  |
| `monitor_base_url` | string \| null |  |  |
| `monitor_api_key_configured` | boolean |  | default `False` |
| `monitor_poll_interval_seconds` | integer | ✓ |  |
| `monitor_online` | boolean \| null |  |  |
| `monitor_status` | string \| null |  |  |
| `monitor_progress_percent` | number \| null |  |  |
| `current_print_name` | string \| null |  |  |
| `monitor_last_message` | string \| null |  |  |
| `monitor_last_error` | string \| null |  |  |
| `current_print_thumbnail_path` | string \| null |  |  |
| `current_print_thumbnail_url` | string \| null |  |  |
| `current_print_thumbnails` | [`PrinterThumbnailResponse`](#schema-printerthumbnailresponse)[] |  |  |
| `history_events` | [`PrinterHistoryEventResponse`](#schema-printerhistoryeventresponse)[] |  |  |
| `monitor_bed_temp_c` | number \| null |  |  |
| `monitor_tool_temp_c` | number \| null |  |  |
| `monitor_bed_target_c` | number \| null |  |  |
| `monitor_tool_target_c` | number \| null |  |  |
| `monitor_current_layer` | integer \| null |  |  |
| `monitor_total_layers` | integer \| null |  |  |
| `monitor_elapsed_seconds` | number \| null |  |  |
| `monitor_remaining_seconds` | number \| null |  |  |
| `monitor_eta_at` | string(date-time) \| null |  |  |
| `monitor_last_event_type` | string \| null |  |  |
| `monitor_last_event_at` | string(date-time) \| null |  |  |
| `monitor_ws_connected` | boolean \| null |  |  |
| `monitor_ws_last_error` | string \| null |  |  |
| `monitor_last_seen_at` | string(date-time) \| null |  |  |
| `monitor_last_updated_at` | string(date-time) \| null |  |  |
| `camera_id` | string(uuid) \| null |  |  |
| `camera_name` | string \| null |  |  |
| `camera_snapshot_url` | string \| null |  |  |
| `camera_mse_ws_url` | string \| null |  |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `PrinterStatus` <a id="schema-printerstatus"></a>

_Type: enum("idle", "printing", "paused", "maintenance", "offline", "error")_

---

### `PrinterThumbnailResponse` <a id="schema-printerthumbnailresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `relative_path` | string | ✓ |  |
| `width` | integer \| null |  |  |
| `height` | integer \| null |  |  |
| `size` | integer \| null |  |  |

---

### `PrinterUpdate` <a id="schema-printerupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `slug` | string \| null |  |  |
| `manufacturer` | string \| null |  |  |
| `model` | string \| null |  |  |
| `serial_number` | string \| null |  |  |
| `location` | string \| null |  |  |
| `status` | [`PrinterStatus`](#schema-printerstatus) \| null |  |  |
| `is_active` | boolean \| null |  |  |
| `notes` | string \| null |  |  |
| `monitor_enabled` | boolean \| null |  |  |
| `monitor_provider` | [`PrinterMonitorProvider`](#schema-printermonitorprovider) \| null |  |  |
| `monitor_base_url` | string \| null |  |  |
| `monitor_api_key` | string \| null |  |  |
| `clear_monitor_api_key` | boolean |  | default `False` |
| `monitor_poll_interval_seconds` | integer \| null |  |  |

---

### `ProductBOMAvailability` <a id="schema-productbomavailability"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string(uuid) | ✓ |  |
| `items` | [`ProductBOMItemResponse`](#schema-productbomitemresponse)[] | ✓ |  |
| `estimated_unit_cost` | string | ✓ |  |
| `buildable_quantity` | integer \| null | ✓ |  |
| `blockers` | string[] |  |  |
| `has_bom` | boolean | ✓ |  |

---

### `ProductBOMItemCreate` <a id="schema-productbomitemcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `component_type` | enum("material", "product", "supply") | ✓ |  |
| `material_id` | string(uuid) \| null |  |  |
| `component_product_id` | string(uuid) \| null |  |  |
| `supply_id` | string(uuid) \| null |  |  |
| `component_name` | string \| null |  |  |
| `component_sku` | string \| null |  |  |
| `quantity` | number \| string | ✓ |  |
| `unit` | string |  | default `'each'`; max 20 |
| `waste_factor_pct` | number \| string |  | default `'0'` |
| `unit_cost` | number \| string \| null |  |  |
| `available_quantity` | number \| string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `ProductBOMItemResponse` <a id="schema-productbomitemresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `component_type` | enum("material", "product", "supply") | ✓ |  |
| `material_id` | string(uuid) \| null |  |  |
| `component_product_id` | string(uuid) \| null |  |  |
| `supply_id` | string(uuid) \| null |  |  |
| `component_name` | string | ✓ |  |
| `component_sku` | string \| null |  |  |
| `quantity` | string | ✓ |  |
| `unit` | string |  | default `'each'`; max 20 |
| `waste_factor_pct` | string |  | default `'0'` |
| `unit_cost` | string | ✓ |  |
| `available_quantity` | string \| integer \| null |  |  |
| `notes` | string \| null |  |  |
| `id` | string(uuid) | ✓ |  |
| `estimated_unit_cost` | string | ✓ |  |
| `is_blocked` | boolean |  | default `False` |
| `blocker` | string \| null |  |  |

---

### `ProductBOMReplace` <a id="schema-productbomreplace"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `items` | [`ProductBOMItemCreate`](#schema-productbomitemcreate)[] |  |  |

---

### `ProductBOMSummary` <a id="schema-productbomsummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string(uuid) | ✓ |  |
| `items` | [`ProductBOMItemResponse`](#schema-productbomitemresponse)[] | ✓ |  |
| `estimated_unit_cost` | string | ✓ |  |
| `buildable_quantity` | integer \| null | ✓ |  |
| `blockers` | string[] |  |  |
| `has_bom` | boolean | ✓ |  |

---

### `ProductBarcodeGenerateResponse` <a id="schema-productbarcodegenerateresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `upc` | string | ✓ | max 12 |
| `format` | string |  | default `'upc-a'` |
| `namespace` | string | ✓ |  |
| `note` | string | ✓ |  |

---

### `ProductCreate` <a id="schema-productcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 200 |
| `description` | string \| null |  |  |
| `material_id` | string(uuid) | ✓ |  |
| `upc` | string \| null |  |  |
| `unit_cost` | number \| string |  | default `'0'` |
| `unit_price` | number \| string |  | default `'0'` |
| `stock_qty` | integer |  | default `0`; ≥ 0.0 |
| `reorder_point` | integer |  | default `5`; ≥ 0.0 |
| `is_active` | boolean |  | default `True` |

---

### `ProductRanking` <a id="schema-productranking"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string \| null | ✓ |  |
| `description` | string | ✓ |  |
| `units_sold` | integer | ✓ |  |
| `gross_sales` | number | ✓ |  |
| `item_cogs` | number | ✓ |  |
| `gross_profit` | number | ✓ |  |
| `platform_fees` | number | ✓ |  |
| `shipping_costs` | number | ✓ |  |
| `contribution_margin` | number | ✓ |  |

---

### `ProductResponse` <a id="schema-productresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `sku` | string | ✓ |  |
| `upc` | string \| null |  |  |
| `name` | string | ✓ |  |
| `description` | string \| null |  |  |
| `material_id` | string(uuid) | ✓ |  |
| `unit_cost` | string | ✓ |  |
| `unit_price` | string | ✓ |  |
| `stock_qty` | integer | ✓ |  |
| `reorder_point` | integer | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `ProductUpdate` <a id="schema-productupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `description` | string \| null |  |  |
| `material_id` | string(uuid) \| null |  |  |
| `upc` | string \| null |  |  |
| `unit_cost` | number \| string \| null |  |  |
| `unit_price` | number \| string \| null |  |  |
| `stock_qty` | integer \| null |  |  |
| `reorder_point` | integer \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `ProfileCreate` <a id="schema-profilecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `rate_pct` | number \| string | ✓ |  |
| `liability_account_id` | string(uuid) | ✓ |  |
| `is_active` | boolean |  | default `True` |

---

### `ProfileResponse` <a id="schema-profileresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `rate_pct` | string | ✓ |  |
| `liability_account_id` | string(uuid) | ✓ |  |
| `is_active` | boolean | ✓ |  |

---

### `ProfileUpdate` <a id="schema-profileupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `rate_pct` | number \| string \| null |  |  |
| `liability_account_id` | string(uuid) \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `ProfitAndLossComparisonResponse` <a id="schema-profitandlosscomparisonresponse"></a>

#322 P2: side-by-side current vs prior-period P&L.

| Field | Type | Req | Notes |
|---|---|---|---|
| `current` | [`ProfitAndLossResponse`](#schema-profitandlossresponse) | ✓ |  |
| `prior` | [`ProfitAndLossResponse`](#schema-profitandlossresponse) | ✓ |  |
| `deltas` | object<string, string> | ✓ |  |

---

### `ProfitAndLossResponse` <a id="schema-profitandlossresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `date_from` | string \| null |  |  |
| `date_to` | string \| null |  |  |
| `basis` | string | ✓ |  |
| `revenue` | [`ProfitAndLossSection`](#schema-profitandlosssection) | ✓ |  |
| `cogs` | [`ProfitAndLossSection`](#schema-profitandlosssection) | ✓ |  |
| `expenses` | [`ProfitAndLossSection`](#schema-profitandlosssection) | ✓ |  |
| `gross_profit` | string | ✓ |  |
| `net_income` | string | ✓ |  |

---

### `ProfitAndLossSection` <a id="schema-profitandlosssection"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `lines` | [`StatementLine`](#schema-statementline)[] | ✓ |  |
| `total` | string | ✓ |  |

---

### `ProfitMarginDataPoint` <a id="schema-profitmargindatapoint"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `date` | string | ✓ |  |
| `job` | string | ✓ |  |
| `product` | string | ✓ |  |
| `margin` | number | ✓ |  |

---

### `ProjectCreate` <a id="schema-projectcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 200 |
| `start_on` | string(date) \| null |  |  |
| `end_on` | string(date) \| null |  |  |
| `notes` | string \| null |  |  |

---

### `ProjectResponse` <a id="schema-projectresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `status` | string | ✓ |  |
| `start_on` | string(date) \| null | ✓ |  |
| `end_on` | string(date) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |

---

### `ProjectUpdate` <a id="schema-projectupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `status` | enum("active", "archived") \| null |  |  |
| `start_on` | string(date) \| null |  |  |
| `end_on` | string(date) \| null |  |  |
| `notes` | string \| null |  |  |

---

### `PromoteRequest` <a id="schema-promoterequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_name` | string | ✓ | max 200 |
| `qty_per_plate` | integer | ✓ |  |
| `num_plates` | integer | ✓ |  |
| `material_id` | string(uuid) | ✓ |  |
| `material_per_plate_g` | number \| string | ✓ |  |
| `print_time_per_plate_hrs` | number \| string | ✓ |  |

---

### `QuoteConvertToJob` <a id="schema-quoteconverttojob"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `job_number` | string | ✓ | max 50 |
| `job_date` | string(date) \| null |  |  |
| `status` | string |  | default `'draft'` |

---

### `QuoteCreate` <a id="schema-quotecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `date` | string(date) | ✓ |  |
| `valid_until` | string(date) \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `product_name` | string | ✓ | max 200 |
| `qty_per_plate` | integer | ✓ |  |
| `num_plates` | integer | ✓ |  |
| `material_id` | string(uuid) | ✓ |  |
| `material_per_plate_g` | number \| string | ✓ |  |
| `print_time_per_plate_hrs` | number \| string | ✓ |  |
| `labor_mins` | number \| string |  | default `'0'` |
| `design_time_hrs` | number \| string \| null |  | default `'0'` |
| `shipping_cost` | number \| string |  | default `'0'` |
| `target_margin_pct` | number \| string |  | default `'40'` |
| `notes` | string \| null |  |  |
| `quote_number` | string \| null |  |  |
| `status` | [`QuoteStatus`](#schema-quotestatus) |  | default `'draft'` |

---

### `QuoteResponse` <a id="schema-quoteresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `quote_number` | string | ✓ |  |
| `date` | string(date) | ✓ |  |
| `valid_until` | string(date) \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `product_name` | string | ✓ |  |
| `qty_per_plate` | integer | ✓ |  |
| `num_plates` | integer | ✓ |  |
| `material_id` | string(uuid) | ✓ |  |
| `total_pieces` | integer | ✓ |  |
| `material_per_plate_g` | string | ✓ |  |
| `print_time_per_plate_hrs` | string | ✓ |  |
| `labor_mins` | string | ✓ |  |
| `design_time_hrs` | string \| null |  |  |
| `electricity_cost` | string | ✓ |  |
| `material_cost` | string | ✓ |  |
| `labor_cost` | string | ✓ |  |
| `design_cost` | string | ✓ |  |
| `machine_cost` | string | ✓ |  |
| `packaging_cost` | string | ✓ |  |
| `shipping_cost` | string | ✓ |  |
| `failure_buffer` | string | ✓ |  |
| `subtotal_cost` | string | ✓ |  |
| `overhead` | string | ✓ |  |
| `total_cost` | string | ✓ |  |
| `cost_per_piece` | string | ✓ |  |
| `target_margin_pct` | string | ✓ |  |
| `price_per_piece` | string | ✓ |  |
| `total_revenue` | string | ✓ |  |
| `platform_fees` | string | ✓ |  |
| `net_profit` | string | ✓ |  |
| `profit_per_piece` | string | ✓ |  |
| `job_id` | string(uuid) \| null |  |  |
| `notes` | string \| null |  |  |
| `status` | string | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `QuoteStatus` <a id="schema-quotestatus"></a>

_Type: enum("draft", "sent", "accepted", "rejected", "expired")_

---

### `QuoteUpdate` <a id="schema-quoteupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `valid_until` | string(date) \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `product_name` | string \| null |  |  |
| `qty_per_plate` | integer \| null |  |  |
| `num_plates` | integer \| null |  |  |
| `material_id` | string(uuid) \| null |  |  |
| `material_per_plate_g` | number \| string \| null |  |  |
| `print_time_per_plate_hrs` | number \| string \| null |  |  |
| `labor_mins` | number \| string \| null |  |  |
| `design_time_hrs` | number \| string \| null |  |  |
| `shipping_cost` | number \| string \| null |  |  |
| `target_margin_pct` | number \| string \| null |  |  |
| `notes` | string \| null |  |  |
| `status` | [`QuoteStatus`](#schema-quotestatus) \| null |  |  |

---

### `RJECreate` <a id="schema-rjecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 200 |
| `cadence` | enum("daily", "weekly", "monthly", "yearly") |  | default `'monthly'` |
| `interval_count` | integer |  | default `1` |
| `start_on` | string(date) | ✓ |  |
| `end_on` | string(date) \| null |  |  |
| `memo` | string \| null |  |  |
| `lines_template` | [`app__api__v1__endpoints__accounting_foundations__TemplateLine`](#schema-app__api__v1__endpoints__accounting_foundations__templateline)[] | ✓ |  |

---

### `RJEResponse` <a id="schema-rjeresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `cadence` | string | ✓ |  |
| `interval_count` | integer | ✓ |  |
| `start_on` | string(date) | ✓ |  |
| `next_run_on` | string(date) | ✓ |  |
| `last_run_on` | string(date) \| null | ✓ |  |
| `end_on` | string(date) \| null | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `memo` | string \| null | ✓ |  |
| `lines_template` | object[] | ✓ |  |
| `last_error` | string \| null | ✓ |  |
| `last_failed_at` | string(date-time) \| null | ✓ |  |

---

### `RJEUpdate` <a id="schema-rjeupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `cadence` | enum("daily", "weekly", "monthly", "yearly") \| null |  |  |
| `interval_count` | integer \| null |  |  |
| `end_on` | string(date) \| null |  |  |
| `is_active` | boolean \| null |  |  |
| `memo` | string \| null |  |  |
| `lines_template` | [`app__api__v1__endpoints__accounting_foundations__TemplateLine`](#schema-app__api__v1__endpoints__accounting_foundations__templateline)[] \| null |  |  |

---

### `RateCreate` <a id="schema-ratecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 100 |
| `value` | number \| string | ✓ |  |
| `unit` | string | ✓ | max 20 |
| `notes` | string \| null |  |  |
| `active` | boolean |  | default `True` |

---

### `RateResponse` <a id="schema-rateresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `value` | string | ✓ |  |
| `unit` | string | ✓ |  |
| `notes` | string \| null |  |  |
| `active` | boolean | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `RateUpdate` <a id="schema-rateupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `value` | number \| string \| null |  |  |
| `unit` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `active` | boolean \| null |  |  |

---

### `ReconciliationCreateRequest` <a id="schema-reconciliationcreaterequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `account_id` | string(uuid) | ✓ |  |
| `statement_end_date` | string(date) | ✓ |  |
| `statement_ending_balance` | number \| string | ✓ |  |
| `notes` | string \| null |  |  |

---

### `ReconciliationDetailResponse` <a id="schema-reconciliationdetailresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `account_id` | string(uuid) | ✓ |  |
| `statement_end_date` | string(date) | ✓ |  |
| `statement_ending_balance` | string | ✓ |  |
| `opening_balance` | string | ✓ |  |
| `book_balance` | string | ✓ |  |
| `variance` | string | ✓ |  |
| `status` | string | ✓ |  |
| `finalized_at` | string(date-time) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `eligible_lines` | [`JournalLineDTO`](#schema-journallinedto)[] | ✓ |  |
| `included_line_ids` | string(uuid)[] | ✓ |  |

---

### `ReconciliationLineToggle` <a id="schema-reconciliationlinetoggle"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `journal_line_id` | string(uuid) | ✓ |  |
| `included` | boolean | ✓ |  |

---

### `RecurringExpenseCreate` <a id="schema-recurringexpensecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `vendor_id` | string(uuid) \| null |  |  |
| `expense_category_id` | string(uuid) \| null |  |  |
| `account_id` | string(uuid) | ✓ |  |
| `description` | string | ✓ | max 255 |
| `amount` | number \| string | ✓ |  |
| `tax_amount` | number \| string |  | default `0` |
| `frequency` | string |  | default `'monthly'` |
| `next_due_date` | string(date) | ✓ |  |
| `payment_method` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `is_active` | boolean |  | default `True` |

---

### `RecurringExpenseGenerate` <a id="schema-recurringexpensegenerate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `as_of_date` | string(date) | ✓ |  |

---

### `RecurringExpenseResponse` <a id="schema-recurringexpenseresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `vendor_id` | string(uuid) \| null |  |  |
| `expense_category_id` | string(uuid) \| null |  |  |
| `account_id` | string(uuid) | ✓ |  |
| `description` | string | ✓ |  |
| `amount` | string | ✓ |  |
| `tax_amount` | string | ✓ |  |
| `frequency` | string | ✓ |  |
| `next_due_date` | string(date) | ✓ |  |
| `payment_method` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `is_active` | boolean | ✓ |  |
| `last_generated_at` | string(date-time) \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |
| `updated_at` | string(date-time) | ✓ |  |

---

### `RecurringExpenseUpdate` <a id="schema-recurringexpenseupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `vendor_id` | string(uuid) \| null |  |  |
| `expense_category_id` | string(uuid) \| null |  |  |
| `account_id` | string(uuid) \| null |  |  |
| `description` | string \| null |  |  |
| `amount` | number \| string \| null |  |  |
| `tax_amount` | number \| string \| null |  |  |
| `frequency` | string \| null |  |  |
| `next_due_date` | string(date) \| null |  |  |
| `payment_method` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `RecurringInvoiceCreate` <a id="schema-recurringinvoicecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 200 |
| `customer_id` | string(uuid) | ✓ |  |
| `cadence` | enum("daily", "weekly", "monthly", "yearly") |  | default `'monthly'` |
| `interval_count` | integer |  | default `1` |
| `start_on` | string(date) | ✓ |  |
| `end_on` | string(date) \| null |  |  |
| `auto_email` | boolean |  | default `False` |
| `line_items_template` | [`app__api__v1__endpoints__recurring_invoices__TemplateLine`](#schema-app__api__v1__endpoints__recurring_invoices__templateline)[] | ✓ |  |
| `due_in_days` | integer |  | default `30` |
| `notes` | string \| null |  |  |

---

### `RecurringInvoiceResponse` <a id="schema-recurringinvoiceresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `customer_id` | string(uuid) | ✓ |  |
| `cadence` | string | ✓ |  |
| `interval_count` | integer | ✓ |  |
| `start_on` | string(date) | ✓ |  |
| `next_run_on` | string(date) | ✓ |  |
| `last_run_on` | string(date) \| null | ✓ |  |
| `end_on` | string(date) \| null | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `auto_email` | boolean | ✓ |  |
| `line_items_template` | object[] | ✓ |  |
| `due_in_days` | integer | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `last_error` | string \| null | ✓ |  |
| `last_failed_at` | string(date-time) \| null | ✓ |  |

---

### `RecurringInvoiceUpdate` <a id="schema-recurringinvoiceupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `cadence` | enum("daily", "weekly", "monthly", "yearly") \| null |  |  |
| `interval_count` | integer \| null |  |  |
| `end_on` | string(date) \| null |  |  |
| `is_active` | boolean \| null |  |  |
| `auto_email` | boolean \| null |  |  |
| `line_items_template` | [`app__api__v1__endpoints__recurring_invoices__TemplateLine`](#schema-app__api__v1__endpoints__recurring_invoices__templateline)[] \| null |  |  |
| `due_in_days` | integer \| null |  |  |
| `notes` | string \| null |  |  |

---

### `RefundInCashRequest` <a id="schema-refundincashrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `cash_account_id` | string(uuid) | ✓ |  |
| `paid_on` | string(date) \| null |  |  |

---

### `RefundRequestBody` <a id="schema-refundrequestbody"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `reason` | string | ✓ | max 255 |

---

### `ReimburseAsBillRequest` <a id="schema-reimburseasbillrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `vendor_id` | string(uuid) | ✓ |  |
| `due_date` | string(date) \| null |  |  |
| `description` | string \| null |  |  |

---

### `ReimburseRequest` <a id="schema-reimburserequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `cash_account_id` | string(uuid) | ✓ |  |
| `paid_on` | string(date) \| null |  |  |

---

### `RejectRequest` <a id="schema-rejectrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `reason` | string \| null |  |  |

---

### `RevenueDataPoint` <a id="schema-revenuedatapoint"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `date` | string | ✓ |  |
| `revenue` | number | ✓ |  |

---

### `RuleCreate` <a id="schema-rulecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `account_id` | string(uuid) \| null |  |  |
| `match_type` | enum("contains", "regex") | ✓ |  |
| `match_pattern` | string | ✓ | max 500 |
| `match_amount_sign` | enum("debit", "credit", "any") |  | default `'any'` |
| `action` | enum("ignore", "create_journal_entry", "create_receipt", "create_payment", "create_inter_account_transfer") |  | default `'ignore'` |
| `category_account_id` | string(uuid) \| null |  |  |
| `counterparty_name` | string \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `vendor_id` | string(uuid) \| null |  |  |
| `transfer_to_account_id` | string(uuid) \| null |  |  |
| `priority` | integer |  | default `100`; ≥ 0.0 |
| `is_active` | boolean |  | default `True` |

---

### `RuleResponse` <a id="schema-ruleresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `account_id` | string(uuid) \| null | ✓ |  |
| `match_type` | string | ✓ |  |
| `match_pattern` | string | ✓ |  |
| `match_amount_sign` | string | ✓ |  |
| `action` | string | ✓ |  |
| `category_account_id` | string(uuid) \| null |  |  |
| `counterparty_name` | string \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `vendor_id` | string(uuid) \| null |  |  |
| `transfer_to_account_id` | string(uuid) \| null |  |  |
| `priority` | integer | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `RuleUpdate` <a id="schema-ruleupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `account_id` | string(uuid) \| null |  |  |
| `match_type` | enum("contains", "regex") \| null |  |  |
| `match_pattern` | string \| null |  |  |
| `match_amount_sign` | enum("debit", "credit", "any") \| null |  |  |
| `action` | enum("ignore", "create_journal_entry", "create_receipt", "create_payment", "create_inter_account_transfer") \| null |  |  |
| `category_account_id` | string(uuid) \| null |  |  |
| `counterparty_name` | string \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `vendor_id` | string(uuid) \| null |  |  |
| `transfer_to_account_id` | string(uuid) \| null |  |  |
| `priority` | integer \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `SOCreate` <a id="schema-socreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `quote_id` | string(uuid) \| null |  |  |
| `issue_date` | string(date) | ✓ |  |
| `expected_ship_date` | string(date) \| null |  |  |
| `notes` | string \| null |  |  |
| `lines` | [`app__api__v1__endpoints__orders__LineIn`](#schema-app__api__v1__endpoints__orders__linein)[] | ✓ |  |

---

### `SaleCreate` <a id="schema-salecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `date` | string(date) | ✓ |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `channel_id` | string(uuid) \| null |  |  |
| `tax_profile_id` | string(uuid) \| null |  |  |
| `tax_treatment` | string |  | default `'seller_collected'` |
| `shipping_charged` | number \| string |  | default `'0'` |
| `shipping_cost` | number \| string |  | default `'0'` |
| `tax_collected` | number \| string |  | default `'0'` |
| `payment_method` | string \| null |  |  |
| `tracking_number` | string \| null |  |  |
| `shipping_recipient_name` | string \| null |  |  |
| `shipping_company` | string \| null |  |  |
| `shipping_address_line1` | string \| null |  |  |
| `shipping_address_line2` | string \| null |  |  |
| `shipping_city` | string \| null |  |  |
| `shipping_state` | string \| null |  |  |
| `shipping_postal_code` | string \| null |  |  |
| `shipping_country` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `status` | [`SaleStatus`](#schema-salestatus) |  | default `'pending'` |
| `items` | [`SaleItemCreate`](#schema-saleitemcreate)[] | ✓ |  |

---

### `SaleItemCreate` <a id="schema-saleitemcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string(uuid) \| null |  |  |
| `job_id` | string(uuid) \| null |  |  |
| `description` | string | ✓ | max 200 |
| `quantity` | integer | ✓ |  |
| `unit_price` | number \| string | ✓ |  |
| `unit_cost` | number \| string |  | default `'0'` |

---

### `SaleItemResponse` <a id="schema-saleitemresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `sale_id` | string(uuid) | ✓ |  |
| `product_id` | string(uuid) \| null |  |  |
| `job_id` | string(uuid) \| null |  |  |
| `description` | string | ✓ |  |
| `quantity` | integer | ✓ |  |
| `unit_price` | string | ✓ |  |
| `line_total` | string | ✓ |  |
| `unit_cost` | string | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |

---

### `SaleListResponse` <a id="schema-salelistresponse"></a>

Lightweight sale for list views (no items).

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `sale_number` | string | ✓ |  |
| `date` | string(date) | ✓ |  |
| `customer_name` | string \| null |  |  |
| `channel_id` | string(uuid) \| null |  |  |
| `channel_name` | string \| null |  |  |
| `payment_method` | string \| null |  |  |
| `tax_profile_id` | string(uuid) \| null |  |  |
| `tax_treatment` | string \| null |  |  |
| `status` | string | ✓ |  |
| `total` | string | ✓ |  |
| `gross_profit` | string | ✓ |  |
| `contribution_margin` | string | ✓ |  |
| `item_count` | integer |  | default `0` |
| `created_at` | string(date-time) \| null |  |  |

---

### `SaleResponse` <a id="schema-saleresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `sale_number` | string | ✓ |  |
| `date` | string(date) | ✓ |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `channel_id` | string(uuid) \| null |  |  |
| `channel_name` | string \| null |  |  |
| `tax_profile_id` | string(uuid) \| null |  |  |
| `tax_treatment` | string | ✓ |  |
| `status` | string | ✓ |  |
| `subtotal` | string | ✓ |  |
| `shipping_charged` | string | ✓ |  |
| `shipping_cost` | string | ✓ |  |
| `platform_fees` | string | ✓ |  |
| `tax_collected` | string | ✓ |  |
| `total` | string | ✓ |  |
| `item_cogs` | string | ✓ |  |
| `gross_profit` | string | ✓ |  |
| `contribution_margin` | string | ✓ |  |
| `payment_method` | string \| null |  |  |
| `tracking_number` | string \| null |  |  |
| `shipping_recipient_name` | string \| null |  |  |
| `shipping_company` | string \| null |  |  |
| `shipping_address_line1` | string \| null |  |  |
| `shipping_address_line2` | string \| null |  |  |
| `shipping_city` | string \| null |  |  |
| `shipping_state` | string \| null |  |  |
| `shipping_postal_code` | string \| null |  |  |
| `shipping_country` | string \| null |  |  |
| `shipping_label_ready` | boolean |  | default `False` |
| `shipping_label_format` | string \| null |  |  |
| `shipping_label_generated_at` | string(date-time) \| null |  |  |
| `shipping_label_last_printed_at` | string(date-time) \| null |  |  |
| `shipping_label_print_count` | integer |  | default `0` |
| `notes` | string \| null |  |  |
| `items` | [`SaleItemResponse`](#schema-saleitemresponse)[] |  | default `[]` |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `SaleStatus` <a id="schema-salestatus"></a>

_Type: enum("pending", "paid", "shipped", "delivered", "refunded", "cancelled")_

---

### `SaleUpdate` <a id="schema-saleupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `date` | string(date) \| null |  |  |
| `customer_id` | string(uuid) \| null |  |  |
| `customer_name` | string \| null |  |  |
| `channel_id` | string(uuid) \| null |  |  |
| `tax_profile_id` | string(uuid) \| null |  |  |
| `tax_treatment` | string \| null |  |  |
| `shipping_charged` | number \| string \| null |  |  |
| `shipping_cost` | number \| string \| null |  |  |
| `tax_collected` | number \| string \| null |  |  |
| `payment_method` | string \| null |  |  |
| `tracking_number` | string \| null |  |  |
| `shipping_recipient_name` | string \| null |  |  |
| `shipping_company` | string \| null |  |  |
| `shipping_address_line1` | string \| null |  |  |
| `shipping_address_line2` | string \| null |  |  |
| `shipping_city` | string \| null |  |  |
| `shipping_state` | string \| null |  |  |
| `shipping_postal_code` | string \| null |  |  |
| `shipping_country` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `status` | [`SaleStatus`](#schema-salestatus) \| null |  |  |

---

### `SalesChannelCreate` <a id="schema-saleschannelcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 100 |
| `platform_fee_pct` | number \| string |  | default `'0'` |
| `fixed_fee` | number \| string |  | default `'0'` |
| `is_active` | boolean |  | default `True` |

---

### `SalesChannelResponse` <a id="schema-saleschannelresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `platform_fee_pct` | string | ✓ |  |
| `fixed_fee` | string | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |

---

### `SalesChannelUpdate` <a id="schema-saleschannelupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `platform_fee_pct` | number \| string \| null |  |  |
| `fixed_fee` | number \| string \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `SalesMetrics` <a id="schema-salesmetrics"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `total_sales` | integer | ✓ |  |
| `gross_sales` | number | ✓ |  |
| `item_cogs` | number | ✓ |  |
| `gross_profit` | number | ✓ |  |
| `platform_fees` | number | ✓ |  |
| `shipping_costs` | number | ✓ |  |
| `contribution_margin` | number | ✓ |  |
| `net_profit` | number \| null |  |  |
| `total_units_sold` | integer | ✓ |  |
| `avg_order_value` | number | ✓ |  |
| `refund_count` | integer | ✓ |  |
| `refund_rate` | number | ✓ |  |
| `revenue_by_channel` | object[] | ✓ |  |
| `payment_method_breakdown` | object[] | ✓ |  |

---

### `SalesReportResponse` <a id="schema-salesreportresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `period_data` | [`SalesReportRow`](#schema-salesreportrow)[] | ✓ |  |
| `top_products` | [`ProductRanking`](#schema-productranking)[] | ✓ |  |
| `channel_breakdown` | [`ChannelBreakdown`](#schema-channelbreakdown)[] | ✓ |  |
| `payment_method_breakdown` | [`PaymentMethodBreakdown`](#schema-paymentmethodbreakdown)[] | ✓ |  |
| `total_orders` | integer | ✓ |  |
| `gross_sales` | number | ✓ |  |
| `item_cogs` | number | ✓ |  |
| `gross_profit` | number | ✓ |  |
| `platform_fees` | number | ✓ |  |
| `shipping_costs` | number | ✓ |  |
| `contribution_margin` | number | ✓ |  |
| `net_profit` | number \| null |  |  |

---

### `SalesReportRow` <a id="schema-salesreportrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `period` | string | ✓ |  |
| `order_count` | integer | ✓ |  |
| `gross_sales` | number | ✓ |  |
| `item_cogs` | number | ✓ |  |
| `gross_profit` | number | ✓ |  |
| `platform_fees` | number | ✓ |  |
| `shipping_costs` | number | ✓ |  |
| `contribution_margin` | number | ✓ |  |

---

### `ScheduleRow` <a id="schema-schedulerow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `period_end` | string(date) | ✓ |  |
| `amount` | string | ✓ |  |

---

### `SettingResponse` <a id="schema-settingresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `key` | string | ✓ |  |
| `value` | string | ✓ |  |
| `notes` | string \| null |  |  |

---

### `SettingUpdate` <a id="schema-settingupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `value` | string | ✓ | max 255 |

---

### `SettlementLineCreate` <a id="schema-settlementlinecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `sale_id` | string(uuid) \| null |  |  |
| `line_type` | string |  | default `'sale'` |
| `description` | string | ✓ | max 255 |
| `amount` | number \| string | ✓ |  |
| `notes` | string \| null |  |  |

---

### `SettlementLineResponse` <a id="schema-settlementlineresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `settlement_id` | string(uuid) | ✓ |  |
| `sale_id` | string(uuid) \| null |  |  |
| `line_type` | string | ✓ |  |
| `description` | string | ✓ |  |
| `amount` | string | ✓ |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `SettlementReconciliationRow` <a id="schema-settlementreconciliationrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `settlement_id` | string(uuid) | ✓ |  |
| `settlement_number` | string | ✓ |  |
| `channel_id` | string(uuid) | ✓ |  |
| `period_start` | string(date) | ✓ |  |
| `period_end` | string(date) | ✓ |  |
| `payout_date` | string(date) | ✓ |  |
| `gross_sales` | string | ✓ |  |
| `marketplace_fees` | string | ✓ |  |
| `adjustments` | string | ✓ |  |
| `reserves_held` | string | ✓ |  |
| `net_deposit` | string | ✓ |  |
| `expected_net` | string | ✓ |  |
| `discrepancy_amount` | string | ✓ |  |

---

### `SettlementReconciliationSummary` <a id="schema-settlementreconciliationsummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `rows` | [`SettlementReconciliationRow`](#schema-settlementreconciliationrow)[] | ✓ |  |
| `total_gross_sales` | string | ✓ |  |
| `total_marketplace_fees` | string | ✓ |  |
| `total_adjustments` | string | ✓ |  |
| `total_reserves_held` | string | ✓ |  |
| `total_net_deposit` | string | ✓ |  |
| `total_expected_net` | string | ✓ |  |
| `total_discrepancy` | string | ✓ |  |

---

### `SourceCreate` <a id="schema-sourcecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `kind` | string |  | default `'watch_directory'` |
| `path` | string | ✓ | max 500 |
| `file_extensions_csv` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `is_active` | boolean |  | default `True` |

---

### `SourceResponse` <a id="schema-sourceresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `kind` | string | ✓ |  |
| `path` | string | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `file_extensions_csv` | string \| null | ✓ |  |
| `last_scan_at` | string(date-time) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |

---

### `SourceUpdate` <a id="schema-sourceupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `path` | string \| null |  |  |
| `file_extensions_csv` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `StartingBalanceLine` <a id="schema-startingbalanceline"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `account_id` | string(uuid) | ✓ |  |
| `amount` | number \| string | ✓ |  |

---

### `StartingBalancesRequest` <a id="schema-startingbalancesrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `as_of` | string(date) | ✓ |  |
| `balances` | [`StartingBalanceLine`](#schema-startingbalanceline)[] | ✓ |  |
| `force` | boolean |  | default `False` |

---

### `StatementImportResponse` <a id="schema-statementimportresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `account_id` | string(uuid) | ✓ |  |
| `source_format` | string | ✓ |  |
| `source_filename` | string | ✓ |  |
| `line_count` | integer | ✓ |  |
| `duplicate_count` | integer | ✓ |  |
| `status` | string | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `StatementLine` <a id="schema-statementline"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `account_code` | string | ✓ |  |
| `account_name` | string | ✓ |  |
| `account_type` | string | ✓ |  |
| `amount` | string | ✓ |  |

---

### `StatementLineResponse` <a id="schema-statementlineresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `import_id` | string(uuid) | ✓ |  |
| `account_id` | string(uuid) | ✓ |  |
| `posted_date` | string(date) | ✓ |  |
| `amount` | string | ✓ |  |
| `description` | string | ✓ |  |
| `fitid` | string \| null | ✓ |  |
| `match_status` | string | ✓ |  |
| `matched_journal_line_id` | string(uuid) \| null | ✓ |  |

---

### `StockLevelRow` <a id="schema-stocklevelrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string | ✓ |  |
| `sku` | string | ✓ |  |
| `name` | string | ✓ |  |
| `stock_qty` | integer | ✓ |  |
| `unit_cost` | number | ✓ |  |
| `stock_value` | number | ✓ |  |
| `reorder_point` | integer | ✓ |  |
| `is_low_stock` | boolean | ✓ |  |

---

### `SupplyAdjust` <a id="schema-supplyadjust"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `quantity_delta` | number \| string | ✓ |  |
| `notes` | string \| null |  |  |

---

### `SupplyCreate` <a id="schema-supplycreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 200 |
| `sku` | string \| null |  |  |
| `category` | string \| null |  |  |
| `unit` | string |  | default `'each'`; max 20 |
| `unit_cost` | number \| string |  | default `'0'` |
| `quantity_on_hand` | number \| string |  | default `'0'` |
| `reorder_point` | number \| string |  | default `'0'` |
| `supplier` | string \| null |  |  |
| `supplier_url` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `active` | boolean |  | default `True` |

---

### `SupplyResponse` <a id="schema-supplyresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `sku` | string \| null |  |  |
| `category` | string \| null |  |  |
| `unit` | string | ✓ |  |
| `unit_cost` | string | ✓ |  |
| `quantity_on_hand` | string | ✓ |  |
| `reorder_point` | string | ✓ |  |
| `supplier` | string \| null |  |  |
| `supplier_url` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `active` | boolean | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |
| `updated_at` | string(date-time) \| null |  |  |

---

### `SupplyUpdate` <a id="schema-supplyupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `sku` | string \| null |  |  |
| `category` | string \| null |  |  |
| `unit` | string \| null |  |  |
| `unit_cost` | number \| string \| null |  |  |
| `quantity_on_hand` | number \| string \| null |  |  |
| `reorder_point` | number \| string \| null |  |  |
| `supplier` | string \| null |  |  |
| `supplier_url` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `active` | boolean \| null |  |  |

---

### `SuspenseReclassifyRequest` <a id="schema-suspensereclassifyrequest"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `journal_line_id` | string(uuid) | ✓ |  |
| `target_account_id` | string(uuid) | ✓ |  |
| `posted_on` | string(date) | ✓ |  |
| `description` | string \| null |  |  |

---

### `TaxLiabilityReportResponse` <a id="schema-taxliabilityreportresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `rows` | [`TaxLiabilityRow`](#schema-taxliabilityrow)[] | ✓ |  |
| `total_seller_collected` | string | ✓ |  |
| `total_marketplace_facilitated` | string | ✓ |  |
| `total_remitted` | string | ✓ |  |
| `total_outstanding_liability` | string | ✓ |  |

---

### `TaxLiabilityRow` <a id="schema-taxliabilityrow"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `tax_profile_id` | string(uuid) | ✓ |  |
| `tax_profile_name` | string | ✓ |  |
| `jurisdiction` | string | ✓ |  |
| `seller_collected` | string | ✓ |  |
| `marketplace_facilitated` | string | ✓ |  |
| `remitted` | string | ✓ |  |
| `outstanding_liability` | string | ✓ |  |
| `is_reverse_charge` | boolean |  | default `False` |
| `reverse_charged_in` | string |  | default `'0'` |
| `reverse_charged_out` | string |  | default `'0'` |

---

### `TaxLiabilitySummary` <a id="schema-taxliabilitysummary"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `date_from` | string(date) \| null |  |  |
| `date_to` | string(date) \| null |  |  |
| `rows` | [`TaxLiabilityRow`](#schema-taxliabilityrow)[] | ✓ |  |
| `total_seller_collected` | string | ✓ |  |
| `total_marketplace_facilitated` | string | ✓ |  |
| `total_remitted` | string | ✓ |  |
| `total_outstanding_liability` | string | ✓ |  |
| `total_reverse_charged_in` | string |  | default `'0'` |
| `total_reverse_charged_out` | string |  | default `'0'` |

---

### `TaxProfileCreate` <a id="schema-taxprofilecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `jurisdiction` | string | ✓ | max 120 |
| `tax_rate` | number \| string |  | default `0` |
| `filing_frequency` | string \| null |  |  |
| `is_marketplace_facilitated` | boolean |  | default `False` |
| `is_active` | boolean |  | default `True` |
| `notes` | string \| null |  |  |

---

### `TaxProfileResponse` <a id="schema-taxprofileresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `jurisdiction` | string | ✓ |  |
| `tax_rate` | string | ✓ |  |
| `filing_frequency` | string \| null |  |  |
| `is_marketplace_facilitated` | boolean | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |
| `updated_at` | string(date-time) | ✓ |  |

---

### `TaxProfileUpdate` <a id="schema-taxprofileupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `jurisdiction` | string \| null |  |  |
| `tax_rate` | number \| string \| null |  |  |
| `filing_frequency` | string \| null |  |  |
| `is_marketplace_facilitated` | boolean \| null |  |  |
| `is_active` | boolean \| null |  |  |
| `notes` | string \| null |  |  |

---

### `TaxRemittanceCreate` <a id="schema-taxremittancecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `tax_profile_id` | string(uuid) | ✓ |  |
| `period_start` | string(date) | ✓ |  |
| `period_end` | string(date) | ✓ |  |
| `remittance_date` | string(date) | ✓ |  |
| `amount` | number \| string | ✓ |  |
| `reference_number` | string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `TaxRemittanceResponse` <a id="schema-taxremittanceresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `tax_profile_id` | string(uuid) | ✓ |  |
| `period_start` | string(date) | ✓ |  |
| `period_end` | string(date) | ✓ |  |
| `remittance_date` | string(date) | ✓ |  |
| `amount` | string | ✓ |  |
| `reference_number` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `TemplateCreate` <a id="schema-templatecreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `scope` | enum("invoice", "quote", "sales_order", "purchase_order", "bill", "expense_claim", "journal_entry") | ✓ |  |
| `name` | string | ✓ | max 120 |
| `is_default` | boolean |  | default `False` |
| `defaults` | object |  |  |

---

### `TemplateResponse` <a id="schema-templateresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `scope` | string | ✓ |  |
| `name` | string | ✓ |  |
| `is_default` | boolean | ✓ |  |
| `defaults` | object | ✓ |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `TemplateUpdate` <a id="schema-templateupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string \| null |  |  |
| `is_default` | boolean \| null |  |  |
| `defaults` | object \| null |  |  |

---

### `TokenResponse` <a id="schema-tokenresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `access_token` | string | ✓ |  |
| `token_type` | string |  | default `'bearer'` |

---

### `TransactionType` <a id="schema-transactiontype"></a>

_Type: enum("production", "sale", "adjustment", "return", "waste")_

---

### `TransferEdit` <a id="schema-transferedit"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `amount` | number \| string \| null |  |  |
| `paid_on` | string(date) \| null |  |  |
| `received_on` | string(date) \| null |  |  |
| `notes` | string \| null |  |  |

---

### `TransferLineIn` <a id="schema-transferlinein"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `kind` | enum("material", "supply", "product") | ✓ |  |
| `material_id` | string(uuid) \| null |  |  |
| `supply_id` | string(uuid) \| null |  |  |
| `product_id` | string(uuid) \| null |  |  |
| `quantity` | number \| string | ✓ |  |

---

### `TransferLineOut` <a id="schema-transferlineout"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `kind` | string | ✓ |  |
| `material_id` | string(uuid) \| null | ✓ |  |
| `supply_id` | string(uuid) \| null | ✓ |  |
| `product_id` | string(uuid) \| null | ✓ |  |
| `quantity` | string | ✓ |  |

---

### `UserCreate` <a id="schema-usercreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `email` | string(email) | ✓ |  |
| `password` | string | ✓ | max 128 |
| `full_name` | string | ✓ | max 200 |
| `role` | [`UserRole`](#schema-userrole) |  | default `'user'` |

---

### `UserResponse` <a id="schema-userresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `email` | string | ✓ |  |
| `full_name` | string | ✓ |  |
| `role` | string | ✓ |  |
| `is_active` | boolean | ✓ |  |
| `created_at` | string(date-time) \| null |  |  |

---

### `UserRole` <a id="schema-userrole"></a>

_Type: enum("admin", "user")_

---

### `UserUpdate` <a id="schema-userupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `email` | string(email) \| null |  |  |
| `full_name` | string \| null |  |  |
| `role` | [`UserRole`](#schema-userrole) \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `ValidationError` <a id="schema-validationerror"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `loc` | string \| integer[] | ✓ |  |
| `msg` | string | ✓ |  |
| `type` | string | ✓ |  |

---

### `ValueUpsert` <a id="schema-valueupsert"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `values` | object | ✓ |  |

---

### `VendorCreate` <a id="schema-vendorcreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | string | ✓ | max 120 |
| `contact_name` | string \| null |  |  |
| `email` | string \| null |  |  |
| `phone` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `is_active` | boolean |  | default `True` |

---

### `VendorResponse` <a id="schema-vendorresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `name` | string | ✓ |  |
| `contact_name` | string \| null |  |  |
| `email` | string \| null |  |  |
| `phone` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `is_active` | boolean | ✓ |  |
| `created_at` | string(date-time) | ✓ |  |
| `updated_at` | string(date-time) | ✓ |  |

---

### `VendorUpdate` <a id="schema-vendorupdate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `contact_name` | string \| null |  |  |
| `email` | string \| null |  |  |
| `phone` | string \| null |  |  |
| `notes` | string \| null |  |  |
| `is_active` | boolean \| null |  |  |

---

### `app__api__v1__endpoints__accounting_foundations__RunResponse` <a id="schema-app__api__v1__endpoints__accounting_foundations__runresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `target_date` | string(date) | ✓ |  |
| `status` | string | ✓ |  |
| `generated_journal_entry_id` | string(uuid) \| null | ✓ |  |
| `error` | string \| null | ✓ |  |
| `triggered_by` | string | ✓ |  |
| `run_at` | string(date-time) | ✓ |  |

---

### `app__api__v1__endpoints__accounting_foundations__TemplateLine` <a id="schema-app__api__v1__endpoints__accounting_foundations__templateline"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `account_id` | string(uuid) | ✓ |  |
| `entry_type` | enum("debit", "credit") | ✓ |  |
| `amount` | number \| string | ✓ |  |
| `description` | string \| null |  |  |

---

### `app__api__v1__endpoints__delivery_notes__LineIn` <a id="schema-app__api__v1__endpoints__delivery_notes__linein"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `description` | string | ✓ | max 255 |
| `quantity` | number \| string | ✓ |  |
| `notes` | string \| null |  |  |

---

### `app__api__v1__endpoints__expense_claims__LineIn` <a id="schema-app__api__v1__endpoints__expense_claims__linein"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `description` | string | ✓ | max 255 |
| `expense_account_id` | string(uuid) | ✓ |  |
| `amount` | number \| string |  | default `0` |
| `line_kind` | enum("expense", "mileage") |  | default `'expense'` |
| `miles` | number \| string \| null |  |  |
| `notes` | string \| null |  |  |

---

### `app__api__v1__endpoints__inter_account_transfers__TransferCreate` <a id="schema-app__api__v1__endpoints__inter_account_transfers__transfercreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `from_account_id` | string(uuid) | ✓ |  |
| `to_account_id` | string(uuid) | ✓ |  |
| `amount` | number \| string | ✓ |  |
| `paid_on` | string(date) | ✓ |  |
| `received_on` | string(date) \| null |  |  |
| `notes` | string \| null |  |  |

---

### `app__api__v1__endpoints__inter_account_transfers__TransferResponse` <a id="schema-app__api__v1__endpoints__inter_account_transfers__transferresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `transfer_number` | string | ✓ |  |
| `from_account_id` | string(uuid) | ✓ |  |
| `to_account_id` | string(uuid) | ✓ |  |
| `amount` | string | ✓ |  |
| `paid_on` | string(date) | ✓ |  |
| `received_on` | string(date) | ✓ |  |
| `journal_entry_id` | string(uuid) | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `created_at` | string(date-time) | ✓ |  |

---

### `app__api__v1__endpoints__locations__TransferCreate` <a id="schema-app__api__v1__endpoints__locations__transfercreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `from_location_id` | string(uuid) | ✓ |  |
| `to_location_id` | string(uuid) | ✓ |  |
| `lines` | [`TransferLineIn`](#schema-transferlinein)[] | ✓ |  |
| `notes` | string \| null |  |  |

---

### `app__api__v1__endpoints__locations__TransferResponse` <a id="schema-app__api__v1__endpoints__locations__transferresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `transfer_number` | string | ✓ |  |
| `from_location_id` | string(uuid) | ✓ |  |
| `to_location_id` | string(uuid) | ✓ |  |
| `status` | string | ✓ |  |
| `shipped_at` | string(date-time) \| null | ✓ |  |
| `received_at` | string(date-time) \| null | ✓ |  |
| `cancelled_at` | string(date-time) \| null | ✓ |  |
| `notes` | string \| null | ✓ |  |
| `lines` | [`TransferLineOut`](#schema-transferlineout)[] | ✓ |  |

---

### `app__api__v1__endpoints__notes__LineIn` <a id="schema-app__api__v1__endpoints__notes__linein"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `description` | string | ✓ | max 255 |
| `quantity` | number \| string | ✓ |  |
| `unit_price` | number \| string | ✓ |  |
| `account_id` | string(uuid) | ✓ |  |

---

### `app__api__v1__endpoints__orders__LineIn` <a id="schema-app__api__v1__endpoints__orders__linein"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `description` | string | ✓ | max 255 |
| `quantity` | number \| string | ✓ |  |
| `unit_price` | number \| string | ✓ |  |

---

### `app__api__v1__endpoints__orders__POCreate` <a id="schema-app__api__v1__endpoints__orders__pocreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `vendor_id` | string(uuid) | ✓ |  |
| `issue_date` | string(date) | ✓ |  |
| `expected_receive_date` | string(date) \| null |  |  |
| `notes` | string \| null |  |  |
| `lines` | [`app__api__v1__endpoints__orders__LineIn`](#schema-app__api__v1__endpoints__orders__linein)[] | ✓ |  |

---

### `app__api__v1__endpoints__production_orders__POCreate` <a id="schema-app__api__v1__endpoints__production_orders__pocreate"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `product_id` | string(uuid) | ✓ |  |
| `output_quantity` | number \| string | ✓ |  |
| `planned_start_date` | string(date) \| null |  |  |
| `notes` | string \| null |  |  |

---

### `app__api__v1__endpoints__recurring_invoices__RunResponse` <a id="schema-app__api__v1__endpoints__recurring_invoices__runresponse"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string(uuid) | ✓ |  |
| `target_date` | string(date) | ✓ |  |
| `status` | string | ✓ |  |
| `generated_invoice_id` | string(uuid) \| null | ✓ |  |
| `error` | string \| null | ✓ |  |
| `triggered_by` | string | ✓ |  |
| `run_at` | string(date-time) | ✓ |  |

---

### `app__api__v1__endpoints__recurring_invoices__TemplateLine` <a id="schema-app__api__v1__endpoints__recurring_invoices__templateline"></a>

| Field | Type | Req | Notes |
|---|---|---|---|
| `description` | string | ✓ |  |
| `quantity` | integer | ✓ |  |
| `unit_price` | number \| string | ✓ |  |
| `notes` | string \| null |  |  |
