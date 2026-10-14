import { LandingNav, Hero, About, Features, Workspaces, Contact, LandingFooter } from "@/pages/landing/LandingSections";

export default function Landing() {
  return (
    <div className="min-h-screen scroll-smooth bg-background" data-testid="landing-page">
      <LandingNav />
      <Hero />
      <About />
      <Features />
      <Workspaces />
      <Contact />
      <LandingFooter />
    </div>
  );
}
