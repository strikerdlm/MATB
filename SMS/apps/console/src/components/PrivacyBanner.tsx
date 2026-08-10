import type { JSX } from "react";

export function PrivacyBanner({ children = "Research identity is pseudonymous and retained only under the approved protocol." }: { readonly children?: string }): JSX.Element {
  return <div className="privacy-banner" role="status"><strong>NON-DISPATCHABLE RESEARCH</strong><span>{children}</span></div>;
}
