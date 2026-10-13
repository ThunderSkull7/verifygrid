# VerifyGrid Frontend

VerifyGrid Frontend is a modern, responsive Single Page Application (SPA) designed for financial audit teams, data analysts, and compliance engineers. Built with React 19, TypeScript, Vite, and Lucide icons, it provides an end-to-end interface to manage projects, upload and profile datasets, configure reconciliation rules, inspect discrepancies, and export audit reports.

---

## 1. Architectural Overview

```text
                      +------------------------------------------+
                      |                 App.tsx                  |
                      |  (Session Guard, Project Selection, Tab) |
                      +--------------------+---------------------+
                                           |
                +--------------------------+--------------------------+
                |                                                     |
                v                                                     v
      +-------------------+                                 +-------------------+
      |   AuthScreen.tsx  |                                 |   Sidebar.tsx &   |
      | (Login, Register) |                                 |    Main Wrapper   |
      +-------------------+                                 +---------+---------+
                                                                      |
                     +------------------------------------------------+
                     |
         +-----------+------------+
         |                        |
         v                        v
+------------------+     +----------------------------------------------------+
| ProjectsView.tsx |     | Dataset Reconciliation Workspace                   |
| (Workspace List, |     |                                                    |
|  Create Modal)   |     |  1. FileUploadSection.tsx (Upload & Profiling)     |
+------------------+     |  2. ReconciliationConfig.tsx (Keys, Rules, Run)   |
                         |  3. VerificationResultsView.tsx (Metrics, Filters, |
                         |                                  Table, Export)   |
                         +-------------------------+--------------------------+
                                                   |
                                                   v
                                        +--------------------+
                                        |    api.ts Client   |
                                        | (Fetch, JWT inject,|
                                        |  Vite proxy /api)  |
                                        +--------------------+
```

---

## 2. Directory Layout & Key Modules

```text
frontend/
├── src/
│   ├── assets/                 # Static branding assets and images
│   ├── components/             # Reusable modular UI components
│   │   ├── AuthScreen.tsx      # Sign-in and account registration view with JWT storage
│   │   ├── FileUploadSection.tsx # File drag-and-drop, upload, and automatic preprocessing display
│   │   ├── ProjectsView.tsx    # Project dashboard, creation modal, and selection
│   │   ├── ReconciliationConfig.tsx # Matching key selection, tolerance config, and run trigger
│   │   ├── Sidebar.tsx         # Left navigation sidebar with tabs, branding, and logout action
│   │   └── VerificationResultsView.tsx # Summary metrics cards, discrepancy table, search, and export actions
│   ├── context/
│   │   ├── AuthContext.tsx     # React Context Provider managing JWT state, user info, and logout
│   │   ├── authContextDef.ts   # Context type definitions and fallback contract
│   │   └── useAuth.ts          # Custom hook to consume the AuthContext safely
│   ├── services/
│   │   └── api.ts              # Typed singleton HTTP client managing endpoints, headers, and file exports
│   ├── types/
│   │   └── index.ts            # Complete TypeScript interface definitions (User, Project, Run, Discrepancy)
│   ├── App.css                 # Component-specific layout enhancements
│   ├── App.tsx                 # Core application controller and layout orchestrator
│   ├── index.css               # Global CSS design system (tokens, dark theme, typography, badges, cards)
│   └── main.tsx                # React DOM entry point wrapping App inside AuthProvider
├── public/                     # Public static assets
├── .env.example                # Frontend environment variable template
├── .oxlintrc.json              # Oxlint linting configuration
├── index.html                  # HTML entry point with meta tags and font styling
├── package.json                # NPM scripts and dependency specifications
├── tsconfig.json               # TypeScript configuration bundle
├── tsconfig.app.json           # Application TypeScript compiler settings
├── tsconfig.node.json          # Vite Node compiler configuration
└── vite.config.ts              # Vite configuration with local `/api` proxy to `http://127.0.0.1:8000`
```

---

## 3. Technology Stack

- **React 19**: Modern component architecture using hooks (`useState`, `useEffect`, `useRef`).
- **TypeScript (strict)**: Full type safety for all API models, request payloads, and component props.
- **Vite 8**: Ultra-fast module bundler with Hot Module Replacement (HMR).
- **Styling**: Curated custom CSS Design System (`index.css`) featuring modern dark mode, glassmorphism card surfaces, and color tokens.
- **Icons**: `lucide-react` for modern icon set.
- **Linter**: `oxlint` for high-performance static analysis.

---

## 4. How the Frontend Works

### 4.1 Authentication State & Session Management

- **AuthContext (`src/context/AuthContext.tsx`)**:
  - Initializes by inspecting `localStorage.getItem('verifygrid_token')`.
  - On mount, calls `/api/v1/auth/me` to populate the active user profile.
  - Automatically listens for `auth:unauthorized` events triggered by `api.ts` on `401 Unauthorized` responses to clear invalid sessions.
- **AuthScreen (`src/components/AuthScreen.tsx`)**:
  - Toggles between Sign In and Sign Up modes.
  - Calls `api.login()` or `api.register()` and stores the bearer token upon success.

### 4.2 Project Management (`src/components/ProjectsView.tsx`)

- Displays available verification projects.
- Provides a modal to create new projects (`POST /api/v1/projects`).
- Allows switching active workspace context, persisting the active project to state.

### 4.3 Ingestion & Profiling Interface (`src/components/FileUploadSection.tsx`)

1. User drops or selects a CSV or XLSX file.
2. The component calls `api.uploadSourceFile(projectId, file)`, posting multipart form data.
3. Upon upload completion, it immediately invokes `api.preprocessFile(projectId, fileId)` to trigger server-side schema profiling.
4. Renders dataset statistics: total rows, detected columns with data types, null counts, and sample values.

### 4.4 Verification Configuration (`src/components/ReconciliationConfig.tsx`)

Once at least 2 datasets are uploaded for a project:

1. User designates one dataset as **Baseline / Source** and the other as **Comparison / Target**.
2. User specifies key matching columns (e.g. `employee_id` or composite `dept, id`).
3. User sets matching parameters:
   - `numeric_tolerance`: Tolerance for numerical and currency float values (e.g., `0.00` or `0.01`).
   - `ignore_case`: Case-insensitive string matching.
   - `ignore_whitespace`: Trimming strings prior to matching.
   - `persistRun`: Checkbox to execute a persistent `POST /runs` workflow in addition to immediate rendering.
4. Submits reconciliation and triggers the results view.

### 4.5 Results Inspection & Export (`src/components/VerificationResultsView.tsx`)

- **Metric Highlights**: Displays top-level audit cards:
  - Total source & target records
  - Matched records & identical match counts
  - Field-level mismatches
  - Missing records (unmatched source vs unmatched target)
  - Duplicate key count
- **Interactive Discrepancy Filter**:
  - Filter by category (`all`, `field_mismatch`, `missing_record`, `duplicate_key`, `none`).
  - Search by key values dynamically across rows.
  - Interactive table displaying source vs. target field differences and row indexes.
- **Export Capabilities**:
  - Users can click **Export CSV**, **Export Excel**, or **Export JSON**.
  - Invokes `api.downloadExport()`, downloading file blobs directly in the browser.

### 4.6 API Integration Layer (`src/services/api.ts`)

- Configured with `BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'`.
- Proxied in development via `vite.config.ts`:

  ```ts
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
    },
  }
  ```

- Automatically injects `Authorization: Bearer <token>` on all requests.
- Parses FastAPI structured error responses (such as Pydantic 422 arrays) into readable error messages.

---

## 5. Environment Configuration

Copy `.env.example` to `.env`:

```ini
VITE_API_BASE_URL=/api/v1
```

*Note: In local development, the Vite dev server proxies `/api` calls directly to `http://127.0.0.1:8000`, so `/api/v1` routes automatically route to the FastAPI backend without CORS friction.*

---

## 6. Local Setup & Execution Guide

### 6.1 Prerequisites

- Node.js (v18+ recommended)
- `npm`

### 6.2 Installation & Running

1. **Navigate to the frontend directory**:

   ```bash
   cd frontend
   ```

2. **Install dependencies**:

   ```bash
   npm install
   ```

3. **Start the development server**:

   ```bash
   npm run dev
   ```

   The application will be live at `http://localhost:5173`.

4. **Linting**:

   ```bash
   npm run lint
   ```

5. **Building for Production**:

   ```bash
   npm run build
   ```

   Generates production bundle in `dist/`.
