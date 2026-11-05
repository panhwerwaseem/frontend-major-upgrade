import Link from 'next/link';

export default function Nav() {
  return (
    <nav>
      <Link href="/">Home</Link>
      <Link href="/dashboard" legacyBehavior>
        <a className="nav-link">Dashboard</a>
      </Link>
    </nav>
  );
}
