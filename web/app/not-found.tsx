import Link from "next/link";

export default function NotFound() {
  return (
    <main className="shell main-content">
      <section className="page-state page-state-empty">
        <div className="state-signal" aria-hidden="true">404</div>
        <p className="eyebrow">Off the fixture list</p>
        <h1>That page does not exist.</h1>
        <p>The competition or match link may have changed with a newer artifact.</p>
        <Link className="button button-dark" href="/">Return to overview</Link>
      </section>
    </main>
  );
}
