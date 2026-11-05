import { Inter } from '@next/font/google';
import Nav from '../components/Nav';

const inter = Inter({ subsets: ['latin'] });

export const metadata = { title: 'Docs' };

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={inter.className}>
      <body>
        <Nav />
        {children}
      </body>
    </html>
  );
}
