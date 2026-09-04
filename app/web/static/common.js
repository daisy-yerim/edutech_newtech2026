export async function api(url, options={}){const response=await fetch(url,options);const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.detail||`요청 실패 (${response.status})`);return data}
export const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export async function pollJob(id,onUpdate){for(;;){const job=await api(`/api/jobs/${id}`);onUpdate?.(job);if(["waiting_review","completed","failed"].includes(job.status))return job;await sleep(1200)}}
export function escapeHtml(value=""){return String(value).replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]))}
