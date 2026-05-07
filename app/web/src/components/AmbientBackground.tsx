export default function AmbientBackground() {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
      {/* Deep gradient base */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#0a0e1a] via-[#0f1628] to-[#1a1f36]" />

      {/* Floating orbs */}
      <div className="absolute top-[-10%] left-[-5%] w-[400px] h-[400px] rounded-full bg-brand-700/10 blur-[100px] animate-float" />
      <div className="absolute bottom-[-15%] right-[-10%] w-[500px] h-[500px] rounded-full bg-accent-cyan/5 blur-[120px] animate-float-delay" />
      <div className="absolute top-[40%] right-[20%] w-[300px] h-[300px] rounded-full bg-accent-amber/5 blur-[80px] animate-float" />

      {/* Grain texture */}
      <div className="grain-overlay" />
    </div>
  );
}
