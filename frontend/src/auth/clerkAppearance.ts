import { dark } from "@clerk/themes";

export const clerkAppearance = {
  baseTheme: dark,
  layout: {
    logoPlacement: "none",
    socialButtonsPlacement: "top",
  },
  variables: {
    borderRadius: "0.5rem",
    colorBackground: "#071111",
    colorBorder: "#1d3434",
    colorDanger: "#ff554f",
    colorForeground: "#eef7f0",
    colorInput: "#050909",
    colorInputForeground: "#eef7f0",
    colorModalBackdrop: "rgba(0, 0, 0, 0.78)",
    colorMuted: "#0a1415",
    colorMutedForeground: "#a1adab",
    colorPrimary: "#72f25f",
    colorPrimaryForeground: "#050909",
    colorRing: "#72f25f",
    colorShadow: "#000000",
    colorSuccess: "#72f25f",
    colorWarning: "#f8c159",
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
        "linear-gradient(180deg, rgba(10, 20, 21, 0.98), rgba(5, 9, 9, 0.98))",
      border: "1px solid #1d3434",
      borderRadius: "0.75rem",
      boxShadow:
        "0 24px 80px rgba(0, 0, 0, 0.62), inset 0 1px 0 rgba(114, 242, 95, 0.16)",
      overflow: "hidden",
    },
    card: {
      backgroundColor: "transparent",
      color: "#eef7f0",
    },
    headerTitle: {
      color: "#eef7f0",
      fontFamily: '"Sora", system-ui, sans-serif',
      fontSize: "1.35rem",
      fontWeight: 700,
      letterSpacing: "0",
    },
    headerSubtitle: {
      color: "#a1adab",
    },
    socialButtonsBlockButton: {
      backgroundColor: "#050909",
      borderColor: "#244041",
      color: "#eef7f0",
      boxShadow: "none",
    },
    socialButtonsBlockButtonText: {
      color: "#eef7f0",
      fontFamily: '"JetBrains Mono", ui-monospace, monospace',
      fontWeight: 600,
    },
    dividerLine: {
      backgroundColor: "#1d3434",
    },
    dividerText: {
      color: "#647371",
    },
    formFieldLabel: {
      color: "#eef7f0",
      fontWeight: 600,
    },
    formFieldInput: {
      backgroundColor: "#050909",
      borderColor: "#244041",
      color: "#eef7f0",
      boxShadow: "none",
    },
    formFieldInput__focus: {
      borderColor: "#72f25f",
      boxShadow: "0 0 0 3px rgba(114, 242, 95, 0.16)",
    },
    formButtonPrimary: {
      backgroundColor: "#72f25f",
      color: "#050909",
      fontFamily: '"JetBrains Mono", ui-monospace, monospace',
      fontWeight: 700,
      textTransform: "lowercase",
      boxShadow: "0 0 18px rgba(114, 242, 95, 0.18)",
    },
    formButtonPrimary__hover: {
      backgroundColor: "#8cff77",
    },
    footer: {
      background:
        "linear-gradient(180deg, rgba(7, 17, 17, 0.92), rgba(5, 9, 9, 0.98))",
      borderTop: "1px solid #1d3434",
    },
    footerAction: {
      display: "none",
    },
    footerPagesLink: {
      color: "#647371",
    },
    modalCloseButton: {
      color: "#a1adab",
    },
  },
} as const;
