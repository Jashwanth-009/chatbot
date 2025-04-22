function askQuestion() {
    const questionInput = document.getElementById("question");
    const responseDiv = document.getElementById("response");
    const loader = document.getElementById("loader");
  
    const question = questionInput.value.trim();
    if (!question) {
      responseDiv.innerText = " Please enter a question.";
      return;
    }
  
    responseDiv.innerText = "";
    loader.classList.remove("hidden");
  
    fetch("/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ question })
    })
      .then(response => response.json())
      .then(data => {
        loader.classList.add("hidden");
        responseDiv.innerText = data.response;
      })
      .catch(err => {
        loader.classList.add("hidden");
        responseDiv.innerText = " Error connecting to server.";
        console.error(err);
      });
  }

