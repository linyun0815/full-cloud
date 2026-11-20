package cn.full.cloud.module.promotion.framework.rpc.config;

import cn.full.cloud.module.infra.api.websocket.WebSocketSenderApi;
import cn.full.cloud.module.member.api.user.MemberUserApi;
import cn.full.cloud.module.product.api.category.ProductCategoryApi;
import cn.full.cloud.module.product.api.sku.ProductSkuApi;
import cn.full.cloud.module.product.api.spu.ProductSpuApi;
import cn.full.cloud.module.system.api.social.SocialClientApi;
import cn.full.cloud.module.system.api.user.AdminUserApi;
import cn.full.cloud.module.trade.api.order.TradeOrderApi;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(value = "promotionRpcConfiguration", proxyBeanMethods = false)
@EnableFeignClients(clients = {ProductSkuApi.class, ProductSpuApi.class, ProductCategoryApi.class,
        MemberUserApi.class, TradeOrderApi.class, AdminUserApi.class, SocialClientApi.class,
        WebSocketSenderApi.class})
public class RpcConfiguration {
}
