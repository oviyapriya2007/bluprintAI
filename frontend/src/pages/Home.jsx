import UploadBox from "../components/UploadBox";

function Home() {
  return (
    <main className="home">
      <section className="hero">
        <h2>
          Turn engineering blueprints into
          <span> actionable data.</span>
        </h2>

        <p>
          Upload a blueprint and automatically extract
          parts, quantities, specifications, and more.
        </p>
      </section>

      <UploadBox />
    </main>
  );
}

export default Home;