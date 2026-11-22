import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { CookieSettingsButton } from "@/components/CookieSettingsButton";

export const metadata: Metadata = {
  title: "Terms and Conditions",
  description: "Terms for using OverBranch and how to manage cookies and analytics.",
  alternates: { canonical: "/terms" },
};

const textLink = "font-medium text-ob-accent underline decoration-ob-accent/40 underline-offset-4 hover:decoration-ob-accent";

export default function TermsPage() {
  return (
    <main className="min-h-dvh bg-ob-bg text-ob-text">
      <header className="border-b border-black/15 bg-[#00CC68] text-black">
        <div className="mx-auto max-w-4xl px-5 pb-10 pt-5 sm:px-8 sm:pb-14">
          <Link href="/" className="inline-flex items-center gap-2 rounded-full border border-black/25 px-3 py-1.5 font-mono text-xs font-bold hover:bg-black hover:text-white">
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            OverBranch home
          </Link>
          <h1 className="mt-8 max-w-3xl font-archivo text-3xl leading-tight tracking-tight sm:text-5xl">
            Terms and Conditions
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-black/80 sm:text-base">
            These terms apply when you use the hosted OverBranch workspace, including its editor, collaboration, and document conversion tools.
          </p>
        </div>
      </header>

      <article className="mx-auto grid max-w-4xl gap-7 px-5 py-9 text-sm leading-7 text-ob-text-2 sm:px-8 sm:py-12 [&_h2]:mb-2 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-ob-text">
        <section>
          <h2>Your account and projects</h2>
          <p>
            Keep your sign-in credentials secure and share projects only with the people you intend to give access to. You keep ownership of the content you upload or create. By using OverBranch, you give it permission to store and process that content as needed to provide the features you use, including displaying shared projects to people you authorize.
          </p>
        </section>

        <section>
          <h2>Acceptable use</h2>
          <p>
            Use the service lawfully and upload only content you have the right to use and share. Respect other users’ privacy and intellectual property. Do not submit malicious files, access projects without permission, or interfere with the availability of the service.
          </p>
        </section>

        <section>
          <h2>Compilation, conversion, and AI assistance</h2>
          <p>
            Review generated LaTeX, converted documents, and AI suggestions before using or publishing them. When you use AI features, the relevant prompts and project content may be sent to the model provider used for that feature.
          </p>
        </section>

        <section>
          <h2>Availability and backups</h2>
          <p>
            OverBranch is in beta. Features may change, and access can be interrupted. Keep a backup of important work and export guest projects before their displayed expiry. The self-hostable source code is available separately under the <a className={textLink} href="https://github.com/abin-karukappallil/overbranch/blob/main/LICENSE">MIT License</a>.
          </p>
        </section>

        <section id="cookies" className="scroll-mt-6 rounded-2xl border border-ob-line bg-ob-card p-5 sm:p-6">
          <h2>Cookies and analytics</h2>
          <p>
            Essential cookies support sign-in, security, and authenticated or guest sessions. Your browser also stores your cookie settings so they can be applied on future visits.
          </p>
          <p className="mt-3">
            When Google Analytics is configured, page-visit measurement is enabled by default and runs without setting analytics cookies. You can turn measurement off without affecting your account or projects. Your choice applies to this browser.
          </p>
          <CookieSettingsButton className="mt-4 cursor-pointer rounded-lg border border-ob-line px-3 py-1.5 text-sm font-medium text-ob-text hover:bg-ob-raised" />
        </section>

        <section>
          <h2>Questions and reports</h2>
          <p>
            For questions about these terms or to report a service issue, use the <a className={textLink} href="https://github.com/abin-karukappallil/overbranch/issues">OverBranch issue tracker</a>. Keep private project content and account details out of public reports.
          </p>
        </section>
      </article>
    </main>
  );
}
