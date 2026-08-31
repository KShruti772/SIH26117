import React from "react";
export default function PageContainer({ children }: { children: React.ReactNode }) { return <main className="aegis-page-container"><div className="aegis-page-content">{children}</div></main>; }
