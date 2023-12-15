
(() => {
    const extensionRoot = '../titanoboa_jupyterlab';
    const getProvider = () => new ethers.BrowserProvider(window.ethereum);
    const stringify = (data) => JSON.stringify(data, (_, v) => (typeof v === 'bigint' ? v.toString() : v));
    const getCookie = (name) => (document.cookie.match(`\\b${name}=([^;]*)\\b`))?.[1];

    /**
     * Calls the callback endpoint with the given token and body
     * todo: cancel callback if ethers raises error (e.g. on cancel)
     */
    async function callback(token, body) {
        const headers = {['X-XSRFToken']: getCookie('_xsrf')};
        const init = { method: 'POST', body: stringify(body), headers };
        const url = `${extensionRoot}/callback/${token}`;
        console.log(`Requesting ${url}`, init);
        const response = await fetch(url, { ...init, headers });
        return response.text();
    }

    const loadSigner = async (token) => {
        console.log(`Loading the user's signer`);
        const provider = getProvider();
        const signer = await provider.getSigner();
        const address = await signer.getAddress();
        return callback(token, address);
    };

    const signTransaction = async (token, transaction) => {
        console.log('Starting to sign transaction');
        const provider = getProvider(window.ethereum);
        const signer = await provider.getSigner();
        const response = await signer.sendTransaction(transaction);
        return callback(token, response);
    };

    // expose functions to window, so they can be called from the BrowserSigner
    window._titanoboa = {loadSigner, signTransaction};
})();
