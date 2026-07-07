import os,logging,json
from datetime import datetime
from urllib.parse import quote
import gspread
from google.oauth2.service_account import Credentials as C
from telegram import Update,InlineKeyboardButton as IKB,InlineKeyboardMarkup as IKM
from telegram.ext import Application,CommandHandler as CH,CallbackQueryHandler as CQH,MessageHandler as MH,filters,ContextTypes,ConversationHandler as CVH
TOK=os.getenv('TELEGRAM_TOKEN','')
SID='1L9jj1K4fXSsPITAMjqt3_SBigw3l8ZDQhH3rcZZP_6g'
CF='credentials.json'
EC,EP,EQ,ET,EA,EG,EGS=range(7)
logging.basicConfig(level=logging.WARNING)
def ss():
 creds_json=os.environ.get('GOOGLE_CREDENTIALS')
 if creds_json:
  info=json.loads(creds_json)
  cred=C.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/spreadsheets'])
 else:
  cred=C.from_service_account_file(CF,scopes=['https://www.googleapis.com/auth/spreadsheets'])
 return gspread.authorize(cred).open_by_key(SID)
def get_records(ws):
 rows=ws.get_all_values()
 if not rows:return []
 h=rows[0];seen={};uh=[]
 for col in h:
  if col in seen:seen[col]+=1;uh.append(col+'_'+str(seen[col]))
  else:seen[col]=0;uh.append(col)
 return [dict(zip(uh,r)) for r in rows[1:] if any(r)]
def clientes():return get_records(ss().worksheet('CLIENTES'))
def stock():return {r['Producto']:r for r in get_records(ss().worksheet('STOCK')) if r.get('Producto')}
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
def guardar_cliente(nombre,tel,manzana='',lote=''):
 ws=ss().worksheet('CLIENTES');rows=ws.get_all_values()
 ids=[int(r[0]) for r in rows[1:] if r and r[0].isdigit()]
 nid=max(ids)+1 if ids else 1
 ws.append_row([nid,nombre,tel,'',manzana,lote,'',''],value_input_option='USER_ENTERED')
 return nid
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
 t_raw=str(t).strip()
 is_intl=t_raw.startswith('+')
 t=t_raw.replace(' ','').replace('-','').replace('+','')
 if not is_intl:
  if t.startswith('0'):t=t[1:]
  if not t.startswith('549'):t='549'+t
 return 'https://wa.me/'+t+'?text='+quote(m)
def msgs_promo():
 rows=ss().worksheet('MENSAJES_PROMO').get_all_values()
 if not rows:return []
 h=rows[0];return [dict(zip(h,r)) for r in rows[1:] if any(r)]
# ── /comunicar ───────────────────────────────────────────────────────────────
async def comunicar(u,c):
 m=await u.message.reply_text('...')
 try:
  msgs=msgs_promo();c.user_data['promo_msgs']=msgs
  if not msgs:await m.edit_text('No hay mensajes en MENSAJES_PROMO');return
  kb=[[IKB(x.get('nomre',x.get('Nombre','')),callback_data='promo|'+str(i))] for i,x in enumerate(msgs)]
  await m.edit_text('¿Qué comunicado querés mandar?',reply_markup=IKM(kb))
 except Exception as e:await m.edit_text('Error:'+str(e))
async def cb_promo(u,c):
 q=u.callback_query;await q.answer()
 try:
  idx=int(q.data.split('|')[1])
  msgs=c.user_data.get('promo_msgs',[])
  if not msgs:await q.edit_message_text('Error: usá /comunicar de nuevo.');return
  texto=msgs[idx].get('texto',msgs[idx].get('Texto',''))
  c.user_data['promo_texto']=texto
  cls=clientes();kb=[]
  for i,cl in enumerate(cls):
   tel=str(cl.get('Telefono','')).strip();nom=cl.get('Nombre','')
   if nom and tel:kb.append([IKB(nom,callback_data='pcl|'+str(i))])
  c.user_data['promo_cls']=cls
  await q.edit_message_text('Elegí el cliente:',reply_markup=IKM(kb) if kb else None)
 except Exception as e:await q.edit_message_text('Error: '+str(e))
async def cb_pcl(u,c):
 q=u.callback_query;await q.answer()
 try:
  idx=int(q.data.split('|')[1])
  cls=c.user_data.get('promo_cls',[])
  texto=c.user_data.get('promo_texto','').replace('\\n','\n')
  cl=cls[idx]
  tel=str(cl.get('Telefono','')).strip()
  try:
   with open('flyer.jpg.png','rb') as f:await q.message.reply_photo(photo=f)
  except:pass
  link=wl(tel,texto)
  await q.message.reply_text(link)
 except Exception as e:await q.message.reply_text('Error: '+str(e))
# ── /gestionar ───────────────────────────────────────────────────────────────
async def gestionar(u,c):
 m=await u.message.reply_text('...')
 try:
  ws=ss().worksheet('VENTAS');rows=get_records(ws)
  pendientes=[r for r in rows if r.get('Estado') not in ('Entregado','Cancelado','')]
  if not pendientes:await m.edit_text('No hay pedidos activos.');return CVH.END
  agrup={}
  for i,r in enumerate(rows):
   if r.get('Estado') not in ('Entregado','Cancelado',''):
    nro=r.get('Nro Pedido',r.get('Numero Pedido','?'))
    agrup.setdefault(str(nro),[]).append((i,r))
  c.user_data['ventas_rows']=rows;c.user_data['ventas_agrup']=agrup
  kb=[]
  for nro,items in sorted(agrup.items(),key=lambda x:x[0]):
   cl=items[0][1].get('Cliente','?');est=items[0][1].get('Estado','?')
   prods=', '.join(str(it[1].get('Producto','')) for it in items)
   kb.append([IKB('#'+str(nro)+' '+cl+' ['+est+'] — '+prods,callback_data='gest|'+str(nro))])
  await m.edit_text('¿Qué pedido querés gestionar?',reply_markup=IKM(kb))
  return EG
 except Exception as e:await m.edit_text('Error: '+str(e));return CVH.END
async def cb_gest(u,c):
 q=u.callback_query;await q.answer()
 nro=q.data.split('|')[1]
 c.user_data['gest_nro']=nro
 agrup=c.user_data.get('ventas_agrup',{})
 items=agrup.get(nro,[])
 if not items:await q.edit_message_text('No encontré ese pedido.');return CVH.END
 cl=items[0][1].get('Cliente','?');est=items[0][1].get('Estado','?')
 prods='\n'.join('- '+str(it[1].get('Cantidad',''))+'x '+str(it[1].get('Producto',''))+' '+fp(lp(it[1].get('Total',0))) for it in items)
 txt='Pedido #'+nro+'\n'+cl+' ['+est+']\n\n'+prods+'\n\nCambiar estado a:'
 kb=[[IKB('Entregado',callback_data='gs|Entregado'),IKB('Pagado',callback_data='gs|Pagado')],
     [IKB('Cancelado',callback_data='gs|Cancelado'),IKB('Reservado',callback_data='gs|Reservado')]]
 await q.edit_message_text(txt,reply_markup=IKM(kb))
 return EGS
async def cb_gs(u,c):
 q=u.callback_query;await q.answer()
 nuevo_estado=q.data.split('|')[1]
 nro=c.user_data.get('gest_nro','')
 try:
  ws=ss().worksheet('VENTAS');all_rows=ws.get_all_values()
  h=all_rows[0] if all_rows else []
  try:col_estado=h.index('Estado')+1
  except:col_estado=8
  try:col_nro=[i for i,x in enumerate(h) if 'Nro' in x or 'Numero' in x or 'Pedido' in x and 'Nro' in x]
  except:col_nro=[]
  col_nro_idx=col_nro[0]+1 if col_nro else 14
  updates=[]
  for i,row in enumerate(all_rows[1:],start=2):
   if len(row)>=col_nro_idx and str(row[col_nro_idx-1]).strip()==str(nro):
    updates.append({'range':f'{chr(64+col_estado)}{i}','values':[[nuevo_estado]]})
  if updates:
   ws.batch_update(updates,value_input_option='USER_ENTERED')
   await q.edit_message_text('Pedido #'+nro+' actualizado a: '+nuevo_estado)
  else:
   await q.edit_message_text('No encontré filas del pedido #'+nro)
 except Exception as e:await q.edit_message_text('Error: '+str(e))
 return CVH.END
# ── comandos simples ──────────────────────────────────────────────────────────
async def start(u,c):
 await u.message.reply_text('Bot Ventas\n/nuevo /stock /pendientes /clientes /gestionar /comunicar /cancelar')
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
  rows=[r for r in get_records(ss().worksheet('VENTAS')) if r.get('Estado')=='Reservado']
  if not rows:await m.edit_text('Sin pendientes.');return
  pc={}
  for r in rows:pc.setdefault(r.get('Cliente','?'),[]).append(r)
  t='PENDIENTES\n\n'
  for cl,its in pc.items():
   t+=cl+'\n'
   for i in its:t+=' '+str(i.get('Cantidad'))+'x '+str(i.get('Producto'))+' '+fp(lp(i.get('Total',0)))+'\n'
  await m.edit_text(t)
 except Exception as e:await m.edit_text('Error:'+str(e))
async def clsl(u,c):
 m=await u.message.reply_text('...')
 try:
  t='CLIENTES\n\n'
  for x in clientes():
   n=x.get('Nombre','')
   if n:t+=n+' '+str(x.get('Telefono',''))+'\n'
  await m.edit_text(t)
 except Exception as e:await m.edit_text('Error:'+str(e))
# ── /nuevo ────────────────────────────────────────────────────────────────────
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
 if v.startswith('_nuevo_|'):
  nombre=v[8:]
  c.user_data['cliente']={'Nombre':nombre,'Telefono':'','ID Cliente':''}
  await q.edit_message_text('Telefono (ej: 1159194973, +447911123456) o escribi "saltar":')
  return ET
 todos=c.user_data.get('cl') or clientes()
 cl=next((x for x in todos if str(x.get('ID Cliente','')).strip()==v.strip()),None)
 if not cl:await q.edit_message_text('Cliente no encontrado (ID:'+v+')');return CVH.END
 c.user_data['cliente']=cl;return await mprod(q,c)
async def txt_cl(u,c):
 nombre=u.message.text.strip()
 todos=c.user_data.get('cl') or clientes()
 matches=[x for x in todos if nombre.lower() in x.get('Nombre','').lower()]
 if matches:
  kb=[[IKB(x.get('Nombre',''),callback_data='cli|'+str(x['ID Cliente']))] for x in matches if x.get('Nombre')]
  kb.append([IKB('Agregar "'+nombre+'" como nuevo',callback_data='cli|_nuevo_|'+nombre)])
  await u.message.reply_text('Encontre estos clientes:',reply_markup=IKM(kb))
  return EC
 c.user_data['cliente']={'Nombre':nombre,'Telefono':'','ID Cliente':''}
 await u.message.reply_text('Telefono (ej: 1159194973, +447911123456) o escribi "saltar":')
 return ET
async def txt_tel(u,c):
 tel=u.message.text.strip()
 cl=c.user_data['cliente']
 if tel.lower()!='saltar':cl['Telefono']=tel
 await u.message.reply_text('Direccion: Manzana y Lote (ej: 29 17) o escribi "saltar":')
 return EA
async def txt_dir(u,c):
 txt=u.message.text.strip()
 cl=c.user_data['cliente']
 manzana='';lote=''
 if txt.lower()!='saltar':
  partes=txt.split()
  manzana=partes[0] if len(partes)>0 else ''
  lote=partes[1] if len(partes)>1 else ''
  cl['Manzana']=manzana;cl['Lote']=lote
 try:
  nid=guardar_cliente(cl['Nombre'],cl.get('Telefono',''),manzana,lote)
  cl['ID Cliente']=nid
  await u.message.reply_text('Cliente guardado!')
 except Exception as e:await u.message.reply_text('No se pudo guardar: '+str(e))
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
   pr=lp(p.get(n,{}).get('Precio público',p.get(n,{}).get('Precio publico',0)))
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
 pr=lp(p.get(v,{}).get('Precio público',p.get(v,{}).get('Precio publico',0)))
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
  MH_='Ya podes pasar a retirar tu pedido por:\n\U0001f4cd Manzana 29 - Lote 17\n\nPodes abonar en efectivo o por transferencia.\nSi pagas en efectivo, avisame con cuanto venis asi te preparo el cambio :)\n\nSi eleges transferencia, el alias es:\n\U0001f4b3 soletissone.mp\n\nTe dejo la ubicacion para que llegues facil:\nhttps://maps.app.goo.gl/SR1qy4qfikJ4F8os6?g_st=ic\n\n¡Gracias por tu compra! \U0001f366'
  MF_='\U0001f95c *¡Tu pedido ya quedo registrado!* \U0001f330\n\nPodes abonar *en efectivo o por transferencia*.\nSi pagas en efectivo, avisame con cuanto asi te preparo el cambio.\nSi preferis transferencia, el alias es:\n\U0001f4b3 *soletissone.mp*\n\n¡Muchas gracias por tu compra! \U0001f95c\U0001f330✨'
  tmpl=MH_ if 'Helados' in tipos else MF_
  mwa='Hola '+cl.get('Nombre','').split()[0]+'!\nTe confirmo tu pedido:\n'+lns_wa+'\n*Total:* '+fp(tg)+'\n'+tmpl
  tel=cl.get('Telefono','');url=wl(tel,mwa) if tel else None
  res='Pedido #'+str(nro)+' guardado!\n\n'+cl.get('Nombre','')+'\n'+lns_tg+'\nTotal: '+fp(tg)
  kb=[[IKB('Enviar WhatsApp',url=url)]] if url else []
  await q.edit_message_text(res,reply_markup=IKM(kb) if kb else None)
 except Exception as e:await q.edit_message_text('Error:'+str(e))
 return CVH.END
async def cancelar(u,c):
 c.user_data.clear();await u.message.reply_text('Cancelado');return CVH.END
def main():
 import asyncio
 loop=asyncio.new_event_loop()
 asyncio.set_event_loop(loop)
 app=Application.builder().token(TOK).build()
 cv_nuevo=CVH(
  entry_points=[CH('nuevo',nuevo)],
  states={
   EC:[CQH(cb_cl,pattern=r'^cli\|'),MH(filters.TEXT&~filters.COMMAND,txt_cl)],
   ET:[MH(filters.TEXT&~filters.COMMAND,txt_tel)],
   EA:[MH(filters.TEXT&~filters.COMMAND,txt_dir)],
   EP:[CQH(cb_pr,pattern=r'^pr\|'),CQH(cb_pr,pattern=r'^ac\|')],
   EQ:[MH(filters.TEXT&~filters.COMMAND,txt_cant)],
  },
  fallbacks=[CH('cancelar',cancelar)],
 )
 cv_gest=CVH(
  entry_points=[CH('gestionar',gestionar)],
  states={
   EG:[CQH(cb_gest,pattern=r'^gest\|')],
   EGS:[CQH(cb_gs,pattern=r'^gs\|')],
  },
  fallbacks=[CH('cancelar',cancelar)],
 )
 app.add_handler(CH('start',start))
 app.add_handler(CH('stock',st))
 app.add_handler(CH('pendientes',pend))
 app.add_handler(CH('clientes',clsl))
 app.add_handler(CH('comunicar',comunicar))
 app.add_handler(CQH(cb_promo,pattern=r'^promo\|'))
 app.add_handler(CQH(cb_pcl,pattern=r'^pcl\|'))
 app.add_handler(cv_nuevo)
 app.add_handler(cv_gest)
 print('Bot iniciado')
 app.run_polling()
if __name__=="__main__":main()
