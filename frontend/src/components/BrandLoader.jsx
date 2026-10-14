export function BrandLoader({ fullScreen = true, label = "Loading" }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-5 bg-white ${fullScreen ? "fixed inset-0 z-[100]" : "min-h-[50vh] rounded-2xl"}`}
      role="status" aria-label={label} data-testid="brand-loader">
      <img src="/civio-logo.png" alt="CIVIO" className="w-48 animate-pulse sm:w-60" />
      <div className="h-1 w-40 overflow-hidden rounded-full bg-slate-100"><div className="h-full w-1/3 animate-[civio-load_1.1s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-[#1E6BFF] to-[#1FD9A8]" /></div>
    </div>
  );
}
