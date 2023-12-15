
(() => {
    const PLUGIN_API_ROOT = '../titanoboa_jupyterlab';
    const getEthersProvider = () => {
        const {ethereum} = window;
        if (!ethereum) throw new Error('No Ethereum browser plugin found');
        return new ethers.BrowserProvider(ethereum);
    };
    const stringify = (data) => JSON.stringify(data, (_, v) => (typeof v === 'bigint' ? v.toString() : v));
    const getCookie = (name) => (document.cookie.match(`\\b${name}=([^;]*)\\b`))?.[1];
    const parsePromise = promise =>
        promise.then(data => ({data})).catch(e => {
            console.error(e.stack || e.message);
            return {error: e.message};
        });

    /** Calls the callback endpoint with the given token and body */
    async function callbackAPI(token, body) {
        const headers = {['X-XSRFToken']: getCookie('_xsrf')};
        const init = {method: 'POST', body: stringify(body), headers};
        const url = `${PLUGIN_API_ROOT}/callback/${token}`;
        const response = await fetch(url, {...init, headers});
        return response.text();
    }

    /** Load the signer via ethers user */
    const loadSigner = async () => {
        const provider = getEthersProvider();
        console.log(`Loading the user's signer`);
        const signer = await provider.getSigner();
        return signer.getAddress();
    };

    /** Sign a transaction via ethers */
    async function signTransaction(transaction) {
        const provider = getEthersProvider();
        console.log('Starting to sign transaction');
        const signer = await provider.getSigner();
        return signer.sendTransaction(transaction);
    }

    const colab = window.google?.colab ?? window.colab;
    console.log('colab', colab);
    if (colab) {
        /** Call the backend when the given function is called, handling errors */
        const registerTarget = (name, func) => {
            colab.kernel.comms.registerTarget(name, channel => {
                console.log(`${name} created`, channel);
                channel.on_msg(async message => {
                    console.log(`${name} called`, channel, message)
                    const args = func(message?.content?.data);
                    const response = await parsePromise(args);
                    channel.send(response);
                });
            });
        };

        registerTarget('loadSigner', loadSigner);
        registerTarget('signTransaction', signTransaction);
    } else {
        /** Call the backend when the given function is called, handling errors */
        const handleCallback = func => async (token, ...args) => {
            const body = await parsePromise(func(...args));
            return callbackAPI(token, body);
        };

        // expose functions to window, so they can be called from the BrowserSigner
        window._titanoboa = {
            loadSigner: handleCallback(loadSigner),
            signTransaction: handleCallback(signTransaction)
        };
    }
})();
