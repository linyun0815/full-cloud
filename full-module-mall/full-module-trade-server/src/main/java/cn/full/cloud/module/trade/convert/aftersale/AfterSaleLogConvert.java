package cn.full.cloud.module.trade.convert.aftersale;

import cn.full.cloud.module.trade.dal.dataobject.aftersale.AfterSaleLogDO;
import cn.full.cloud.module.trade.service.aftersale.bo.AfterSaleLogCreateReqBO;
import org.mapstruct.Mapper;
import org.mapstruct.factory.Mappers;

@Mapper
public interface AfterSaleLogConvert {

    AfterSaleLogConvert INSTANCE = Mappers.getMapper(AfterSaleLogConvert.class);

    AfterSaleLogDO convert(AfterSaleLogCreateReqBO bean);

}
