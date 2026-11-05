export default function Card({ title, body, tone }) {
  return (
    <section className={'card card--' + tone}>
      <h2>{title}</h2>
      <p>{body}</p>
    </section>
  );
}

Card.defaultProps = { tone: 'plain' };
