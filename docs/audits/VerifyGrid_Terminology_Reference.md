# VerifyGrid Terminology Reference Document

**Batch 3: Terminology and Language Simplification**  
*Audience:* College administrators, departmental office staff, and organizational personnel working with Excel spreadsheets, alongside accounting/financial auditors.

---

## 1. Approved User-Facing Terminology

The table below defines the approved, plain-language terminology for all visible frontend surfaces (headers, navigation, cards, tables, drawers, buttons, empty states, and notifications).

| Concept Area | Approved Terminology | Definition & User Context |
|---|---|---|
| **Core Action** | **Compare records** / **Comparison** | The primary operation of comparing two or more spreadsheets to detect differences. |
| **Organization Workspace** | **Organization Records** | The verification mode for comparing institutional rosters (academic, hostel, library, membership). |
| **Financial Workspace** | **Financial Records** / **Financial Auditing** | The audit mode for comparing financial ledgers, bank transactions, and gateway settlements. |
| **Baseline File** | **Main file to trust** / **Main file** | The authoritative spreadsheet whose values are considered the baseline standard. |
| **Comparison File** | **File to check** / **Comparison file** | The secondary or target spreadsheet being evaluated against the main file. |
| **Matching Key** | **Matching column** / **Matching key** | The unique column (e.g. Student ID, Invoice Number) used to align corresponding rows. |
| **Possible Key** | **Possible matching column** | A candidate column detected during inspection with high uniqueness. |
| **Column Alignment** | **Match column names** | The step where columns meaning the same thing across different files are paired together. |
| **Canonical Field** | **Standard column name** | The standardized name for an attribute shared across multiple files. |
| **File Intake** | **Upload files** / **Upload spreadsheets** | Adding Excel (.xlsx) or CSV files into the workspace session. |
| **Data Container** | **Spreadsheet** / **File** | A single uploaded Excel sheet or CSV document (replaces abstract "Dataset"). |
| **Mismatch / Delta** | **Difference** | Any row value that does not match between compared spreadsheets. |
| **Data Quality Issues** | **Items needing attention** / **Data issues** | Formatting anomalies, malformed dates, or shifted cells detected during file intake. |
| **Missing Values** | **Empty cells** | Cells that contain no data or null entries. |
| **Secondary Key** | **Backup matching column** | An alternate column tried in priority order when the primary matching column is missing or blank. |
| **Pre-flight Check** | **Check your data** / **Check data** | Quality inspection run on a spreadsheet before comparing records. |
| **Quarantine** | **Items needing review** | Rows flagged with data anomalies that can be included or excluded before comparison. |
| **Saved Configurations** | **Saved setup (template)** | A reusable recipe storing column matches, worksheet selections, and comparison settings. |
| **Template Application**| **Apply to uploaded files** / **Use saved setup** | Validating and reusing a saved configuration on new spreadsheets. |
| **Execution** | **Compare Records** / **Comparison run** | The active process of running the comparison engine across files. |
| **Processing State** | **Checking…** / **Comparing…** | The active progress indicator while the system validates or compares data. |

---

## 2. Replaced Terminology Matrix

The following table documents terms replaced across frontend navigation, controls, headers, drawers, and modal dialogs.

| Replaced Technical Term | Approved User-Facing Replacement | Where Applied |
|---|---|---|
| *Reconciliation* | **Compare records** / **Comparison** | Navigation, Wizard stepper, Action buttons, Result summaries |
| *Organization Verification* | **Organization Records** | Sidebar navigation, App tab metadata, Workspace header |
| *Financial Dataset Reconciliation* | **Financial Records** | Workspace header, Subtitles, Topbar breadcrumb |
| *Multi-Source Dataset Ingestion* | **Upload Your Spreadsheets** / **Upload files** | Step 1 header, Drag-and-drop dropzone, File lists |
| *Primary Source* / *Primary Golden* | **Main file to trust** | Role selectors, File badges, Column mapping headers |
| *Secondary Source* / *Target* | **File to check** | Role selectors, File badges, Diff tables |
| *Source Alias* | **Short Name** | Step 2 file setup table |
| *Key Column(s)* | **Matching Column** | Step 2 table, Step 4 exception grid, Audit history |
| *AI & Heuristic Join Key Recommendations* | **Suggested Matching Columns** | Step 2 recommendation banner |
| *Apply this Key* | **Use this column** | Step 2 recommendation action button |
| *Column Mapping* | **Match Column Names** | Step 2 section header, instructions, table |
| *Field* | **Standard column name** | Step 2 mapping table headers, diff tables |
| *Fallback Matching* | **Backup matching columns** | Step 2 fallback configuration, Result badges |
| *Unified Join Key* | **Standard matching column name** | Step 2 input field |
| *Back to Ingestion* | **Back to upload** | Step 2 navigation button |
| *Proceed to Rules* | **Continue to settings** | Step 2 navigation button |
| *Reconciliation Rules & Tolerances* | **Comparison Settings & Tolerances** | Step 3 header and descriptions |
| *Numeric & Measurement Tolerances* | **Number & Amount Differences** | Step 3 numeric rule card |
| *Settlement Date Window* | **Payment / Transaction Date Range** | Step 3 date rule card |
| *Cross-System Status Equivalence* | **Equivalent Status Terms** | Step 3 status equivalence card |
| *Text Cleaning* | **Text & Spacing Cleanup** | Step 3 string normalization card |
| *Structured Record Predicates & Compound Filters* | **Filter Records Before Comparing (optional)** | Step 3 record filter card |
| *Add Predicate* | **Add filter** | Step 3 predicate creation button |
| *One-to-Many (1:N) & Split-Payment Aggregation* | **Split Payments & Installments (1-to-many)** | Step 3 aggregation card |
| *Live Rule Impact Dry-Run & Simulation* | **Preview Comparison Results** | Step 3 preview panel |
| *Preview Rule Impact* | **Preview Results** | Step 3 dry-run action button |
| *Projected Passes / Projected Exceptions* | **Expected Matches / Expected Differences** | Step 3 preview metrics |
| *Execute Reconciliation Run* | **Compare Records** | Step 3 primary execution button |
| *Multi-Source Exception Grid & Lineage* | **Comparison Results & Differences** | Step 4 header and subtitle |
| *Total Evaluated* | **Total Records Compared** | Step 4 & Step 5 metric summaries |
| *Identical Matches* | **Matching Records** | Step 4, Step 5, Status badges |
| *Field Mismatches* | **Records with Differences** | Step 4, Step 5, Result filters |
| *Missing Across Sources* | **Missing Across Spreadsheets** | Step 4 summary bar |
| *Verification Coverage* | **Comparison Coverage** | Step 4 coverage box |
| *Attribute Comparisons Completed* | **Column Checks Completed** | Step 4 coverage metrics |
| *Attributes Not Checked* | **Columns Not Checked** | Step 4 coverage metrics |
| *Invalid Identity Keys* | **Items Needing Review (Blank Keys)** | Step 4 coverage metrics |
| *Proceed to Sign-off* | **Continue to review** | Step 4 navigation buttons |
| *Run Sign-off, Audit Entry & Exports* | **Review & Download Reports** | Step 5 header and subtitle |
| *Export Discrepancy & Reconciliation Reports* | **Download Comparison & Difference Reports** | Step 5 export actions |
| *Sign-off Notes / Auditor Attestation* | **Review Notes / Sign-off Attestation** | Step 5 review textarea |
| *Sign-off & Seal Reconciliation* | **Sign off & Save Comparison** | Step 5 primary action button |
| *Start New Reconciliation* | **Start New Comparison** | Step 5 reset button |
| *Pre-flight Profiling & Quarantine* | **Check Data & Review Items** | Sliding sidecar drawer header |
| *Eligible for Run / Excluded Rows* | **Ready to Compare / Excluded from Comparison** | Quarantine drawer KPI metrics |
| *Blocking Flags* | **Blocking Issues** | Quarantine drawer KPI metrics |
| *Column Profiles & Keys* | **Columns & Matching Keys** | Quarantine drawer tab |
| *Flagged Quarantine Records* | **Flagged Items Needing Review** | Quarantine drawer tab |
| *Candidate Key Evaluation* | **Possible Matching Columns** | Quarantine drawer candidate key section |
| *Viable Key / Collisions & Nulls* | **Good Matching Key / Duplicates or Empty Cells** | Candidate key status badges |
| *Zero records in quarantine* | **No items needing review** | Quarantine empty state |
| *RECORD INSPECTOR* | **RECORD DETAILS** | Record inspector header |
| *Gross Exposure / Net Variance* | **Total Difference Amount / Net Difference** | Record inspector materiality KPI panel |
| *Source Amount / Target Amount* | **Main File Amount / Comparison File Amount** | Record inspector amount boxes |
| *Decision Diagnostics & Failed Rules* | **Why This Record Flagged a Difference** | Record inspector failure diagnosis |
| *Side-by-Side Field Comparison (Raw vs. Normalized)* | **Side-by-Side Column Comparison** | Record inspector diff table |
| *null* (in data cells) | **empty** | Diff table blank cell indicator |
| *Bulk Cluster Review* | **Group Review: Common Differences** | Bulk review modal title |
| *Total Exposure* | **Total difference amount** | Bulk review modal impact metric |
| *Resolution Decision* | **Review Decision** | Bulk review modal tab & selector |
| *API connected / API offline* | **Connected / Offline** | Topbar status badge |
| *Cryptographic Audit Trail & Hash Chain* / *Tamper-Proof* | **Tamper-Evident Audit Trail** | Cryptographic audit viewer header |

---

## 3. Terms Intentionally Retained and Technical Rationale

1. **"Financial Auditing"**
   - *Rationale:* In financial and enterprise contexts, "Audit" is a formal, legally significant term recognized by CPAs and internal audit teams. Retained in the mode selector and report headers.
2. **"Project"**
   - *Rationale:* Universally understood across organizational tools (Excel, Google Drive, Jira) as a top-level workspace. Replacing it with "Folder" or "Workspace" creates ambiguity regarding access control boundaries.
3. **"Saved Template" / "Template" (alongside "Saved setup")**
   - *Rationale:* End-users frequently recognize "Templates" from Excel and Word; preserving "Save as new template" satisfies established mental models while clarifying helper copy.
4. **"Step 2: Name Your Files & Matching Keys" & "Add files & pre-flight"**
   - *Rationale:* Retained in exact text string form on headings and stepper anchors to maintain strict regression contract guarantees with existing automated end-to-end component harnesses.
5. **Underlying API Endpoints, Database Models, and JSON Schemas**
   - *Rationale:* All database columns (`is_primary`, `match_status`, `discrepancy_category`, `quarantine_reason`, `source_row_index`) remain 100% untouched to ensure backend cryptographic validation, Alembic migration lineage, and rule engine invariants are preserved.
6. **"Tamper-Evident Audit Trail" (strictly avoiding "Tamper-Proof")**
   - *Rationale:* VerifyGrid uses SHA-256 cryptographic hash chaining to guarantee mathematical *tamper-evidence* (unauthorized modifications or omissions are detectable upon chain verification). The phrase "tamper-proof" is avoided because it overstates the security guarantee by implying physical prevention rather than cryptographic detection.

---

## 4. Context-Specific Wording Exceptions

1. **Financial Mode vs. Organization Mode:**
   - In Organization mode, files are named "Academic Records", "Hostel Allocation", "Library Records"; rows represent *students, members, or registrants*.
   - In Financial mode, files are named "ERP Ledger", "Bank Statement", "Gateway Receipts"; rows represent *transactions, invoices, or settlements*.
   - Tolerances in Financial mode refer to currency thresholds (`$0.02`), while in Organization mode they refer to exact record matching (`0`).
2. **"Master Records (Golden)" in Exports:**
   - While "Golden Record" is technical data-management jargon, "Master Records (Golden)" bridges non-technical staff understanding ("Master Record") with enterprise audit expectations ("Golden Record").
3. **Status Badges:**
   - Simple generic terms (`Match`, `Difference`, `Checked`) are used for primary row badges, but specific reason codes (e.g., `MALFORMED_DATE` $\rightarrow$ `Invalid Date Format`) are displayed inside detail drawers to provide actionable clarity.

---

## 5. Terminology Awaiting Product Decisions

1. **"Reconciliation" in Technical Reports:**
   - *Question:* Should generated PDF and XLSX audit reports completely replace the word "Reconciliation" with "Comparison Report", or retain "Reconciliation" in the report title for regulatory compliance?
   - *Current Recommendation:* Retain "Reconciliation Audit Report" on formal financial exports while using "Comparison Report" on organization exports.
2. **"Quarantine" in Backend Error Responses:**
   - *Question:* Should API error payloads eventually deprecate the term `quarantine` in favor of `review_queue` in future API v2?
   - *Current Recommendation:* Retain `quarantine` in internal API schemas for backward compatibility; translate to "Items needing review" strictly at the frontend display layer.
3. **Composite Key Notation:**
   - *Question:* Is `column_a + column_b` notation intuitive for non-technical administrators, or should a visual multi-select chip UI be adopted in Batch 4?
   - *Current Recommendation:* Address in Batch 4 workflow simplification.

