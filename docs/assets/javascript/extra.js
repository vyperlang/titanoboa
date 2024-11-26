document.addEventListener('DOMContentLoaded', function() {
    const functionAdmonitions = document.querySelectorAll('.admonition.function');
    
    functionAdmonitions.forEach(admonition => {
        const content = admonition.innerHTML;
        const sourceCodeMatch = content.match(/source-code:\s*(https?:\/\/\S+)/);
        if (sourceCodeMatch) {
            const sourceCodeUrl = sourceCodeMatch[1];
            
            // Remove the source-code line from the visible content
            admonition.innerHTML = content.replace(/source-code:\s*https?:\/\/\S+\s*/, '');

            const title = admonition.querySelector('.admonition-title');
            if (title) {
                title.style.position = 'relative';  // Add this line
                const sourceCodeButton = document.createElement('a');
                sourceCodeButton.textContent = 'Source Code';
                sourceCodeButton.href = sourceCodeUrl;
                sourceCodeButton.target = '_blank';
                sourceCodeButton.classList.add('source-code-button');
                
                title.appendChild(sourceCodeButton);
            }
        }
    });
});
