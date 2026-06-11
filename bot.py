import os,logging
from datetime import datetime
from urllib.parse import quote
import gspread
from google.oauth2.service_account import Credentials as C
from telegram import Update,InlineKeyboardButton as IKB,InlineKeyboardMarkup as IKM
from telegram.ext import Application,CommandHandler as CH,CallbackQueryHandler as CQH,MessageHandler as MH,filters,ContextTypes,ConversationHandler as CVH
import os,logging
from datetime import datetime
from urllib.parse import quote
import gspread
from google.oauth2.service_account import Credentials as C
from telegram import Update,InlineKeyboardButton as IKB,InlineKeyboardMarkup as IKM
from telegram.ext import Application,CommandHandler as CH,CallbackQueryHandler as CQH,MessageHandler as MH,filters,ContextTypes,ConversationHandler as CVH
TOK='8723725863:AAHKlRoHkk7fqV0TlMDpLhazXVT6ExHpjxM'
SID='1L9jj1K4fXSsPITAMjqt3_SBigw3l8ZDQhH3rcZZP_6g'
CF='credentials.json'
EC,EP,EQ=range(3)
logging.basicConfig(level=logging.WARNING)
def ss():
 import os,json
 creds_json=os.environ.get('GOOGLE_CREDENTIALS')
 if creds_json:
  info=json.loads(creds_json)
  cred=C.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/spreadsheets'])
 else:
  cred=C.from_service_account_file(CF,scopes=['https://www.googleapis.com/auth/spreadsheets'])
 return gspread.authorize(cred).open_by_key(SID)
def clientes():return ss().worksheet('CLIENTES').get_all_records()
def stock():return {r['Producto']:r for r in ss().worksheet('STOCK').get_all_records() if r.get('Producto')}
def precios():
 ws=ss().worksheet('CATALOGO');rows=ws.get_all_values()
 if not rows:return {}
 h=rows[0];res={}
 for row in rows[1:]:
  d=dict(zip(h,row));prod=d.get('Producto','').strip()
  if not prod:continue
  res[prod]=d
 return res
def ultimo():
 c=ss().worksheet('VENTAS').col_values(14)
 n=[int(v) for v in c[1:] if str(v).isdigit()]
 return max(n) if n else 0
def guardar(filas):
 ws=ss().worksheet('VENTAS')
 col=ws.col_values(1)
 last=0
 for i,v in enumerate(col):
  if v and v not in('Fecha','Nombre'):last=i+1
 for i,fila in enumerate(filas):
  r=last+1+i
  fila[10]=f'=SI(O(D{r}="";E{r}="");"";E{r}*L{r})'
 ws.update(range_name=f'A{last+1}',values=filas,value_input_option='USER_ENTERED')
def fp(v):
 try:
  n=int(round(v)) if isinstance(v,(int,float)) else int(round(float(str(v).replace('$','').replace(' ','').replace('.','').replace(',','.'))))
  return '$'+format(n,',').replace(',','.')
 except:return str(v)
def lp(v):
 try:return float(str(v).replace('$','').replace('.','').replace(',','.'))
 except:return 0.0
def wl(t,m):
 t=str(t).strip().replace(' ','').replace('-','')
 if t.startswith('0'):t=t[1:]
 if not t.startswith('549'):t='549'+t
 return 'https://wa.me/'+t+'?text='+quote(m)
async def start(u,c):
 await u.message.reply_text('Bot Ventas\n/nuevo /stock /pendientes /clientes /cancelar')
async def st(u,c):
 m=await u.message.reply_text('...')
 try:
  s=stock();t='STOCK\n\nHELADOS\n'
  for n,d in [(k,v) for k,v in s.items() if v.get('Tipo producto')=='Helados']:
   di=int(d.get('Disponible') or 0)
   t+=('OK' if di>0 else 'XX')+' '+n+': '+str(di)+'\n'
  t+='\nFRUTOS SECOS\n'
  for n,d in [(k,v) for k,v in s.items() if v.get('Tipo producto')!='Helados' and k]:
   di=int(d.get('Disponible') or 0)
   t+=('OK' if di>0 else 'XX')+' '+n+': '+str(di)+'\n'
  await m.edit_text(t)
 except Exception as e:await m.edit_text('Error:'+str(e))
async def pend(u,c):
 m=await u.message.reply_text('...')
 try:
  rows=[r for r in ss().worksheet('VENTAS').get_all_records() if r.get('Estado')=='Reservado']
  if not rows:await m.edit_text('Sin pendientes.');return
  pc={}
  for r in rows:pc.setdefault(r.get('Cliente','?'),[]).append(r)
  t='PENDIENTES\n\n'
  for cl,its in pc.items():
   t+=cl+'\n'
   for i in its:t+=' '+str(i.get('Cantidad'))+'x '+str(i.get('Producto'))+' '+fp(i.get('Total',0))+'\n'
  await m.edit_text(t)
 except Exception as e:await m.edit_text('Error:'+str(e))
async def cls(u,c):
 m=await u.message.reply_text('...')
 try:
  t='CLIENTES\n\n'
  for x in clientes():
   n=x.get('Nombre','')
   if n:t+=n+' '+str(x.get('Telefono',''))+'\n'
  await m.edit_text(t)
 except Exception as e:await m.edit_text('Error:'+str(e))
async def nuevo(u,c):
 c.user_data.clear();c.user_data['items']=[]
 m=await u.message.reply_text('...')
 try:
  cl=clientes();c.user_data['cl']=cl
  kb=[[IKB(x.get('Nombre',''),callback_data='cli|'+str(x['ID Cliente']))] for x in cl if x.get('Nombre')]
  kb.append([IKB('Nombre nuevo',callback_data='cli|_m_')])
  await m.edit_text('Para quien?',reply_markup=IKM(kb))
  return EC
 except Exception as e:await m.edit_text('Error:'+str(e));return CVH.END
async def cb_cl(u,c):
 q=u.callback_query;await q.answer();_,v=q.data.split('|',1)
 if v=='_m_':await q.edit_message_text('Nombre:');return EC
 cl=next((x for x in c.user_data.get('cl',[]) if str(x['ID Cliente'])==v),None)
 if not cl:await q.edit_message_text('No encontrado');return CVH.END
 c.user_data['cliente']=cl;return await mprod(q,c)
async def txt_cl(u,c):
 c.user_data['cliente']={'Nombre':u.message.text.strip(),'Telefono':'','ID Cliente':''}
 return await mprod(u,c)
async def mprod(o,c):
 try:
  s=stock();p=precios();c.user_data['s']=s;c.user_data['p']=p
  its=c.user_data.get('items',[]);cl=c.user_data['cliente']['Nombre']
  t='Pedido '+cl+'\n'
  if its:
   sub=sum(i['q']*i['pr'] for i in its);t+='\nItems:\n'
   for i in its:t+=' '+str(i['q'])+'x '+i['n']+': '+fp(i['q']*i['pr'])+'\n'
   t+=' Sub: '+fp(sub)+'\n'
  t+='\nElegir producto:'
  kb=[]
  for n,d in [(k,v) for k,v in s.items() if int(v.get('Disponible') or 0)>0]:
   di=int(d.get('Disponible') or 0);ti=d.get('Tipo producto','')
   em='H' if ti=='Helados' else 'F'
   pr=lp(p.get(n,{}).get('Precio publico',0))
   kb.append([IKB(em+' '+n+' ('+str(di)+') '+fp(pr),callback_data='pr|'+n)])
  if its:kb.append([IKB('Confirmar',callback_data='ac|ok')])
  kb.append([IKB('Cancelar',callback_data='ac|no')])
  if hasattr(o,'edit_message_text'):await o.edit_message_text(t,reply_markup=IKM(kb))
  else:await o.message.reply_text(t,reply_markup=IKM(kb))
  return EP
 except Exception as e:
  if hasattr(o,'edit_message_text'):await o.edit_message_text('Error:'+str(e))
  else:await o.message.reply_text('Error:'+str(e))
  return CVH.END
async def cb_pr(u,c):
 q=u.callback_query;await q.answer();tp,v=q.data.split('|',1)
 if tp=='ac':
  if v=='ok':return await confirmar(q,c)
  await q.edit_message_text('Cancelado');return CVH.END
 s=c.user_data.get('s',{});p=c.user_data.get('p',{})
 di=int(s.get(v,{}).get('Disponible') or 0)
 pr=lp(p.get(v,{}).get('Precio publico',0))
 c.user_data['psel']=v;c.user_data['prsel']=pr
 await q.edit_message_text(v+'\n'+fp(pr)+'\nDisp: '+str(di)+'\n\nCuantos?')
 return EQ
async def txt_cant(u,c):
 txt=u.message.text.strip()
 if not txt.isdigit() or int(txt)<=0:await u.message.reply_text('Numero mayor a 0:');return EQ
 cant=int(txt);prod=c.user_data['psel'];pr=c.user_data['prsel']
 s=c.user_data['s'];di=int(s.get(prod,{}).get('Disponible') or 0)
 if cant>di:await u.message.reply_text('Max '+str(di)+':');return EQ
 its=c.user_data['items'];ex=next((i for i in its if i['n']==prod),None)
 if ex:ex['q']+=cant
 else:its.append({'n':prod,'q':cant,'pr':pr,'t':s.get(prod,{}).get('Tipo producto','')})
 await u.message.reply_text('OK: '+str(cant)+'x '+prod)
 return await mprod(u,c)
async def confirmar(q,c):
 its=c.user_data.get('items',[]);cl=c.user_data.get('cliente',{})
 if not its:await q.edit_message_text('Sin items');return CVH.END
 await q.edit_message_text('Guardando...')
 try:
  fecha=datetime.now().strftime('%d/%m/%Y');nro=ultimo()+1
  p=c.user_data.get('p',{});s=c.user_data.get('s',{})
  tg=sum(i['q']*i['pr'] for i in its)
  filas=[]
  for i in its:
   n=i['n'];q2=i['q'];pr=i['pr'];tot=q2*pr;ti=i['t']
   di=int(s.get(n,{}).get('Disponible') or 0);ch='OK' if di>=q2 else 'SIN STOCK'
   mu=lp(p.get(n,{}).get('Margen unitario',0))
   filas.append([fecha,cl.get('Nombre',''),ti,n,q2,pr,tot,'Reservado',di,ch,mu*q2,mu,'',nro,'','',''])
  guardar(filas)
  tipos=set(i['t'] for i in its)
  lns_wa='\n'.join('- '+i['n']+' x'+str(i['q']) for i in its)
  lns_tg='\n'.join(' '+str(i['q'])+'x '+i['n']+': '+fp(i['q']*i['pr']) for i in its)
  MH='Ya podés pasar a retirar tu pedido por:\n\U0001f4cd Manzana 29 - Lote 17\n\nPodés abonar en efectivo o por transferencia.\nSi pagás en efectivo, avisame con cuánto venís así te preparo el cambio :)\n\nSi elegís transferencia, el alias es:\n\U0001f4b3 soletissone.mp\n\nTe dejo la ubicación para que llegues fácil:\nhttps://maps.app.goo.gl/SR1qy4qfikJ4F8os6?g_st=ic\n\n¡Gracias por tu compra! \U0001f366'
  MF='\U0001f95c *¡Tu pedido ya quedó registrado!* \U0001f330\n\nPodés abonar *en efectivo o por transferencia*.\nSi pagás en efectivo, avisame con cuánto así te preparo el cambio.\nSi preferís transferencia, el alias es:\n\U0001f4b3 *soletissone.mp*\n\n¡Muchas gracias por tu compra! \U0001f95c\U0001f330✨'
  tmpl=MH if 'Helados' in tipos else MF
  mwa='Hola '+cl.get('Nombre','')+'!\nTe confirmo tu pedido:\n'+lns_wa+'\n*Total:* '+fp(tg)+'\n'+tmpl
  tel=cl.get('Telefono','');url=wl(tel,mwa) if tel else None
  res='Pedido #'+str(nro)+' guardado!\n\n'+cl.get('Nombre','')+'\n'+lns_tg+'\nTotal: '+fp(tg)
  kb=[[IKB('Enviar WhatsApp',url=url)]] if url else []
  await q.edit_message_text(res,reply_markup=IKM(kb) if kb else None)
 except Exception as e:await q.edit_message_text('Error:'+str(e))
 return CVH.END
async def cancelar(u,c):
 c.user_data.clear();await u.message.reply_text('Cancelado');return CVH.END
def main():
 app=Application.builder().token(TOK).build()
 cv=CVH(
  entry_points=[CH('nuevo',nuevo)],
  states={
   EC:[CQH(cb_cl,pattern=r'^cli\|'),MH(filters.TEXT&~filters.COMMAND,txt_cl)],
   EP:[CQH(cb_pr,pattern=r'^pr\|'),CQH(cb_pr,pattern=r'^ac\|')],
   EQ:[MH(filters.TEXT&~filters.COMMAND,txt_cant)],
  },
  fallbacks=[CH('cancelar',cancelar)],
 )
 app.add_handler(CH('start',start))
 app.add_handler(CH('stock',st))
 app.add_handler(CH('pendientes',pend))
 app.add_handler(CH('clientes',cls))
 app.add_handler(cv)
 print('Bot iniciado!')
 import asyncio
 loop=asyncio.new_event_loop()
 asyncio.set_event_loop(loop)
 app.run_polling()
if __name__=="__main__":main()
