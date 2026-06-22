import { dark } from "@clerk/themes";

export const clerkAppearance = {
  baseTheme: dark,
  layout: {
    logoPlacement: "none",
    socialButtonsPlacement: "top",
  },
  variables: {
    borderRadius: "0.5rem",
    colorBackground: "#161515",
    colorBorder: "#3a3026",
    colorDanger: "#d4775f",
    colorForeground: "#f8e0b8",
    colorInput: "#101010",
    colorInputForeground: "#f8e0b8",
    colorModalBackdrop: "rgba(0, 0, 0, 0.78)",
    colorMuted: "#181818",
    colorMutedForeground: "#ccb088",
    colorPrimary: "#ecc997",
    colorPrimaryForeground: "#101010",
    colorRing: "#ecc997",
    colorShadow: "#000000",
    colorSuccess: "#e8c088",
    colorWarning: "#b89358",
    fontFamily: '"Sora", system-ui, sans-serif',
    fontFamilyButtons: '"JetBrains Mono", ui-monospace, monospace',
  },
  elements: {
    modalBackdrop: {
      backdropFilter: "blur(4px)",
      backgroundColor: "rgba(0, 0, 0, 0.78)",
    },
    modalContent: {
      backgroundColor: "transparent",
      boxShadow: "none",
    },
    cardBox: {
      background:
        "linear-gradient(135deg, rgba(236, 201, 151, 0.055), rgba(184, 147, 88, 0.02), transparent 54%), #181818",
      border: "1px solid rgba(236, 201, 151, 0.13)",
      borderRadius: "0.75rem",
      boxShadow:
        "0 24px 80px rgba(0, 0, 0, 0.62), inset 0 1px 0 rgba(248, 224, 184, 0.035)",
      overflow: "hidden",
    },
    card: {
      backgroundColor: "transparent",
      color: "#f8e0b8",
    },
    headerTitle: {
      color: "#f8e0b8",
      fontFamily: '"Sora", system-ui, sans-serif',
      fontSize: "1.35rem",
      fontWeight: 700,
      letterSpacing: "0",
    },
    headerSubtitle: {
      color: "#ccb088",
    },
    socialButtonsBlockButton: {
      backgroundColor: "#101010",
      borderColor: "#3a3026",
      color: "#f8e0b8",
      boxShadow: "none",
    },
    socialButtonsBlockButtonText: {
      color: "#f8e0b8",
      fontFamily: '"JetBrains Mono", ui-monospace, monospace',
      fontWeight: 600,
    },
    dividerLine: {
      backgroundColor: "#3a3026",
    },
    dividerText: {
      color: "#8a765b",
    },
    formFieldLabel: {
      color: "#f8e0b8",
      fontWeight: 600,
    },
    formFieldInput: {
      backgroundColor: "#101010",
      borderColor: "#3a3026",
      color: "#f8e0b8",
      boxShadow: "none",
    },
    formFieldInput__focus: {
      borderColor: "#ecc997",
      boxShadow: "0 0 0 3px rgba(236, 201, 151, 0.16)",
    },
    formButtonPrimary: {
      backgroundColor: "#ecc997",
      color: "#101010",
      fontFamily: '"JetBrains Mono", ui-monospace, monospace',
      fontWeight: 700,
      textTransform: "lowercase",
      boxShadow: "0 8px 22px rgba(236, 201, 151, 0.16)",
    },
    formButtonPrimary__hover: {
      backgroundColor: "#f8e0b8",
    },
    footer: {
      background:
        "linear-gradient(180deg, rgba(22, 21, 21, 0.92), rgba(16, 16, 16, 0.98))",
      borderTop: "1px solid rgba(236, 201, 151, 0.13)",
    },
    footerAction: {
      display: "none",
    },
    footerPagesLink: {
      color: "#8a765b",
    },
    modalCloseButton: {
      color: "#ccb088",
    },
  },
} as const;
