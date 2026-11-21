# FuelFlux Frontend Application

FuelFlux Web UI is a modern, responsive, enterprise SaaS dashboard built with Next.js 14 App Router, TypeScript, Tailwind CSS, Lucide Icons, and Zustand.

## Technology Stack
- **Framework:** Next.js 14 (App Router)
- **Language:** TypeScript 5
- **Styling:** Tailwind CSS 3.4
- **State Management:** Zustand 5
- **Icons & Graphics:** Lucide React, Framer Motion, Recharts
- **Forms & Validation:** React Hook Form, Zod

## Folder Architecture

```text
frontend/
├── app/                  # Next.js App Router pages and role layouts
│   ├── (auth)/          # Authentication (login, register, forgot-password, select-role)
│   ├── admin/           # Platform superadmin control center
│   ├── dashboard/       # Fuel station owner / dealer operations
│   ├── employee/        # Station attendant portal
│   ├── investor/        # Station investor & stakeholder analytics
│   └── logistic/        # Fleet manager & credit portal
├── components/          # Reusable UI components by domain
│   ├── admin/           # Superadmin components
│   ├── compliance/      # Statutory compliance cards and document managers
│   ├── dashboard/       # Station operations components
│   ├── employee/        # Attendant punch & shift cards
│   ├── feedback/        # Toast, spinners, notifications
│   ├── layouts/         # Role-based headers, navigation sidebars
│   ├── shared/          # Universal reusable cards, search bars
│   └── ui/              # Primitives (Button, Input, Modal, Badge, Dropdown)
├── data/                # Static mock configurations and options
├── lib/                 # Core utilities, Axios HTTP client, formatters
├── public/              # Brand logos, icons, vector assets
├── services/            # API client services mapped to backend v1 endpoints
├── stores/              # Zustand global client stores
├── types/               # TypeScript definitions
├── middleware.ts        # Next.js route protection & role session validation
├── next.config.mjs      # Production Next.js configuration
├── package.json         # Dependencies & scripts
└── tsconfig.json        # TypeScript configuration with @/* path aliases
```

## Getting Started

### Installation
```bash
npm install
```

### Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

### Type Checking & Linting
```bash
# Type check without emitting
npx tsc --noEmit

# ESLint validation
npm run lint
```

### Production Build
```bash
npm run build
npm start
```
