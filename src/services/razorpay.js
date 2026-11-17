let checkoutScriptPromise;

export function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  if (checkoutScriptPromise) return checkoutScriptPromise;

  checkoutScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';

    function cleanup() {
      clearTimeout(timeout);
      script.onload = null;
      script.onerror = null;
    }

    function fail() {
      cleanup();
      script.remove();
      reject(new Error('The payment gateway did not load.'));
    }

    const timeout = setTimeout(fail, 15_000);
    script.onerror = fail;
    script.onload = () => {
      if (!window.Razorpay) {
        fail();
        return;
      }
      cleanup();
      resolve();
    };
    document.body.appendChild(script);
  }).finally(() => {
    checkoutScriptPromise = undefined;
  });

  return checkoutScriptPromise;
}
