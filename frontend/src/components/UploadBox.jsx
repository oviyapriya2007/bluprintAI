import { useNavigate } from "react-router-dom";

function UploadBox() {
  const navigate = useNavigate();

  const handleFileChange = (event) => {
    const file = event.target.files[0];

    if (file) {
      navigate("/dashboard");
    }
  };

  return (
    <div className="upload-box">
      <div className="upload-icon">📄</div>

      <h2>Upload your blueprint</h2>

      <p>
        Upload an engineering drawing or blueprint to analyze
        parts, quantities, and specifications.
      </p>

      <label className="upload-button">
        Choose PDF

        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          hidden
          onChange={handleFileChange}
        />
      </label>

      <span className="upload-hint">
        PDF, PNG or JPG • Max 20 MB
      </span>
    </div>
  );
}

export default UploadBox;

