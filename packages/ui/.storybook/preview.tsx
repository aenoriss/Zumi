import type { Preview, Decorator } from "@storybook/react-vite";
import { useEffect } from "react";
import "../src/styles/index.css";

const withTheme: Decorator = (Story, ctx) => {
  const theme = (ctx.globals.theme as string) ?? "paper";
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.body.style.background = "var(--color-room-field)";
    document.body.style.color = "var(--color-text-default)";
  }, [theme]);
  return (
    <div className="font-body text-md text-text-default">
      <Story />
    </div>
  );
};

const preview: Preview = {
  globalTypes: {
    theme: {
      description: "Zumi theme",
      toolbar: {
        title: "Theme",
        icon: "paintbrush",
        items: [
          { value: "paper", title: "Paper" },
          { value: "midnight", title: "Midnight" },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: "paper" },
  decorators: [withTheme],
  parameters: {
    backgrounds: { disable: true },
    a11y: { test: "error" },
    controls: { expanded: true },
    options: {
      storySort: { order: ["Tokens", "Foundations", "Components", "Patterns"] },
    },
  },
};
export default preview;
