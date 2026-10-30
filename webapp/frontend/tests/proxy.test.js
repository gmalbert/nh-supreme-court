import test from 'node:test';
import assert from 'node:assert/strict';
import { onRequest } from '../functions/[[path]].js';

const env = { NHSC_API_ORIGIN: 'https://api.example.test', NHSC_ACCESS_CLIENT_ID: 'service-id', NHSC_ACCESS_CLIENT_SECRET: 'service-secret' };

test('fails closed without an HTTPS origin and Access credentials', async () => {
  const request = new Request('https://site.example.test/api/health');
  assert.equal((await onRequest({request,env:{...env,NHSC_API_ORIGIN:'http://api.example.test'}})).status,503);
  assert.equal((await onRequest({request,env:{...env,NHSC_ACCESS_CLIENT_SECRET:''}})).status,503);
  assert.equal((await onRequest({request:new Request('https://site.example.test/random'),env})).status,404);
});

test('forwards method, query and body using only configured Access credentials', async () => {
  const original = globalThis.fetch;
  let captured;
  globalThis.fetch = async request => {captured = request; return new Response('ok',{headers:{'set-cookie':'CF_Authorization=secret','content-type':'text/plain'}});};
  try {
    const request = new Request('https://site.example.test/api/research/search?q=a%2Bb',{method:'POST',headers:{'content-type':'application/json','cf-access-client-id':'attacker','cookie':'private=1'},body:'{"query":"test"}'});
    const response = await onRequest({request,env});
    assert.equal(captured.url,'https://api.example.test/api/research/search?q=a%2Bb');
    assert.equal(captured.method,'POST');
    assert.equal(await captured.text(),'{"query":"test"}');
    assert.equal(captured.headers.get('cf-access-client-id'),'service-id');
    assert.equal(captured.headers.get('cf-access-client-secret'),'service-secret');
    assert.equal(captured.headers.get('cookie'),null);
    assert.equal(response.headers.get('set-cookie'),null);
  } finally { globalThis.fetch=original; }
});

test('rewrites same-origin redirects and rejects external redirects', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch=async()=>new Response(null,{status:307,headers:{location:'https://api.example.test/api/example/?x=1'}});
    const request = new Request('https://site.example.test/api/example');
    assert.equal((await onRequest({request,env})).headers.get('location'),'/api/example/?x=1');
    globalThis.fetch=async()=>new Response(null,{status:302,headers:{location:'https://other.example.test/'}});
    assert.equal((await onRequest({request,env})).status,502);
  } finally { globalThis.fetch=original; }
});
